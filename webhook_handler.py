"""
Saweria Webhook Handler untuk Drama Bot
Handles incoming payments from Saweria and activates premium users
"""

import os
import json
from datetime import datetime, timedelta
from flask import Flask, request, jsonify
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Supabase configuration
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

# Saweria configuration
SAWERIA_SECRET = os.getenv('SAWERIA_SECRET', 'your_saweria_webhook_secret')

# Package prices (in Rupiah)
PACKAGE_PRICES = {
    '1day': 3000,
    '7day': 10000,
    '30day': 25000,
    '1year': 50000
}

def get_package_duration(package_type: str) -> timedelta:
    """Get package duration"""
    durations = {
        '1day': timedelta(days=1),
        '7day': timedelta(days=7),
        '30day': timedelta(days=30),
        '1year': timedelta(days=365)
    }
    return durations.get(package_type, timedelta(days=1))

def determine_package_from_amount(amount: int) -> str:
    """Determine package type from payment amount"""
    for package, price in PACKAGE_PRICES.items():
        if amount >= price:
            return package
    return '1day'  # Default to smallest package

def activate_premium_user(user_id: int, package_type: str, payment_id: int):
    """Activate premium for user"""
    try:
        # Calculate expiry date
        duration = get_package_duration(package_type)
        expiry = datetime.now() + duration
        
        # Update user premium status
        result = supabase.table('users').update({
            'is_premium': True,
            'premium_expiry': expiry.isoformat(),
            'total_paid': supabase.raw(f'total_paid + {PACKAGE_PRICES[package_type]}')
        }).eq('telegram_id', user_id).execute()
        
        # Update payment status
        supabase.table('payments').update({
            'status': 'completed',
            'completed_at': datetime.now().isoformat()
        }).eq('id', payment_id).execute()
        
        print(f"✅ User {user_id} activated with {package_type} package")
        return True
        
    except Exception as e:
        print(f"❌ Error activating user {user_id}: {e}")
        return False

@app.route('/webhook/saweria', methods=['POST'])
def saweria_webhook():
    """Handle Saweria webhook"""
    try:
        # Parse webhook data
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data received'}), 400
        
        # Extract payment information
        donation_id = data.get('id')  # Saweria donation ID
        amount_raw = int(data.get('amount_raw', 0))  # Raw amount in Rupiah
        amount_display = data.get('etc', {}).get('amount_to_display', amount_raw)  # Display amount
        qr_string = data.get('etc', {}).get('qr_string', '')  # QR code string
        message = data.get('message', '')  # Message from donor
        donator_name = data.get('donator_name', 'Anonymous')
        donator_email = data.get('donator_email', '')
        created_at = data.get('created_at', '')
        donation_type = data.get('type', 'donation')
        
        # Use display amount for package determination, raw amount for actual payment
        amount = amount_display
        
        print(f"💰 Webhook received: {donation_id} | {donator_name} | Raw: {amount_raw} | Display: {amount_display} | Type: {donation_type}")
        
        # Try to extract payment code from message first, then fallback to telegram ID
        telegram_id = None
        payment_code = None
        
        try:
            import re
            
            # Look for payment code pattern (8 character alphanumeric)
            code_match = re.search(r'[A-F0-9]{8}', message.upper())
            if code_match:
                payment_code = code_match.group()
                
                # Find user by payment code
                pending_payment = supabase.table('payments').select('user_id').eq('payment_code', payment_code).eq('status', 'pending').execute()
                if pending_payment.data:
                    telegram_id = pending_payment.data[0]['user_id']
                    print(f"🎯 Found user {telegram_id} via payment code {payment_code}")
            
            # Fallback: try to extract telegram ID directly
            if not telegram_id:
                numbers = re.findall(r'\d{8,15}', message)
                if numbers:
                    telegram_id = int(numbers[0])
                    print(f"🎯 Found Telegram ID {telegram_id} directly in message")
                    
        except Exception as e:
            print(f"Error extracting payment info: {e}")
        
        # If we found a user, process payment automatically
        if telegram_id:
            # Check if user exists
            user_result = supabase.table('users').select('*').eq('telegram_id', telegram_id).execute()
            if user_result.data:
                # Update payment record if using payment code
                if payment_code:
                    supabase.table('payments').update({
                        'saweria_donation_id': donation_id,
                        'amount': amount_raw,  # Store raw amount
                        'amount_display': amount_display,  # Store display amount
                        'qr_string': qr_string,  # Store QR code string
                        'status': 'completed',
                        'completed_at': datetime.now().isoformat(),
                        'webhook_data': {**data, 'matched_via': 'payment_code'}
                    }).eq('payment_code', payment_code).execute()
                    
                    # Get payment details for activation
                    payment_result = supabase.table('payments').select('*').eq('payment_code', payment_code).execute()
                    if payment_result.data:
                        payment = payment_result.data[0]
                        package_type = payment['package_type']
                        payment_id = payment['id']
                        
                        # Activate premium
                        success = activate_premium_user(telegram_id, package_type, payment_id)
                        
                        if success:
                            return jsonify({
                                'message': 'Payment processed automatically via payment code',
                                'user_id': telegram_id,
                                'package_type': package_type,
                                'amount_raw': amount_raw,
                                'amount_display': amount_display,
                                'payment_code': payment_code,
                                'donation_id': donation_id
                            }), 200
                else:
                    # Direct telegram ID match - create new payment record
                    package_type = determine_package_from_amount(amount)
                    
                    payment_data = {
                        'user_id': telegram_id,
                        'package_type': package_type,
                        'amount': amount_raw,  # Store raw amount
                        'amount_display': amount_display,  # Store display amount
                        'saweria_donation_id': donation_id,
                        'qr_string': qr_string,  # Store QR code string
                        'status': 'completed',
                        'webhook_data': {**data, 'matched_via': 'telegram_id'},
                        'completed_at': datetime.now().isoformat()
                    }
                    
                    payment_result = supabase.table('payments').insert(payment_data).execute()
                    payment_id = payment_result.data[0]['id']
                    
                    # Activate premium
                    success = activate_premium_user(telegram_id, package_type, payment_id)
                    
                    if success:
                        return jsonify({
                            'message': 'Payment processed automatically via Telegram ID',
                            'user_id': telegram_id,
                            'package_type': package_type,
                            'amount_raw': amount_raw,
                            'amount_display': amount_display,
                            'donation_id': donation_id
                        }), 200
        
        # Check if payment already exists (prevent duplicate processing)
        existing_payment = supabase.table('payments').select('*').eq('saweria_donation_id', donation_id).execute()
        if existing_payment.data:
            print(f"⚠️ Payment {donation_id} already processed")
            return jsonify({'message': 'Payment already processed'}), 200
        
        # If no automatic match found, store as pending for manual assignment
        # Determine package type from amount
        package_type = determine_package_from_amount(amount)
        
        # Store pending payment for manual assignment
        payment_data = {
            'user_id': None,  # Will be assigned when admin matches with user
            'package_type': package_type,
            'amount': amount_raw,  # Store raw amount
            'amount_display': amount_display,  # Store display amount
            'saweria_donation_id': donation_id,
            'qr_string': qr_string,  # Store QR code string
            'status': 'pending_assignment',  # New status for unassigned payments
            'webhook_data': {
                **data,
                'donator_name': donator_name,
                'donator_email': donator_email,
                'message': message,
                'created_at': created_at,
                'donation_type': donation_type
            }
        }
        
        payment_result = supabase.table('payments').insert(payment_data).execute()
        payment_id = payment_result.data[0]['id']
        
        print(f"💰 Payment {payment_id} stored, waiting for user assignment")
        
        return jsonify({
            'message': 'Payment received and stored',
            'payment_id': payment_id,
            'package_type': package_type,
            'amount_raw': amount_raw,
            'amount_display': amount_display,
            'donation_id': donation_id,
            'status': 'pending_assignment'
        }), 200
            
    except Exception as e:
        print(f"❌ Webhook error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/assign-payment', methods=['POST'])
def assign_payment():
    """Assign pending payment to user (for admin use)"""
    try:
        data = request.get_json()
        payment_id = data.get('payment_id')
        telegram_id = int(data.get('telegram_id'))
        
        if not payment_id or not telegram_id:
            return jsonify({'error': 'Payment ID and Telegram ID required'}), 400
        
        # Check if user exists
        user_result = supabase.table('users').select('*').eq('telegram_id', telegram_id).execute()
        if not user_result.data:
            return jsonify({'error': 'User not found'}), 404
        
        # Get payment details
        payment_result = supabase.table('payments').select('*').eq('id', payment_id).execute()
        if not payment_result.data:
            return jsonify({'error': 'Payment not found'}), 404
        
        payment = payment_result.data[0]
        
        if payment['status'] != 'pending_assignment':
            return jsonify({'error': 'Payment already assigned or processed'}), 400
        
        # Assign payment to user and activate premium
        package_type = payment['package_type']
        
        # Update payment record
        supabase.table('payments').update({
            'user_id': telegram_id,
            'status': 'completed',
            'completed_at': datetime.now().isoformat()
        }).eq('id', payment_id).execute()
        
        # Activate premium
        success = activate_premium_user(telegram_id, package_type, payment_id)
        
        if success:
            return jsonify({
                'message': 'Payment assigned and premium activated',
                'user_id': telegram_id,
                'package_type': package_type,
                'amount_raw': payment.get('amount', 0),
                'amount_display': payment.get('amount_display', payment.get('amount', 0)),
                'donation_id': payment.get('saweria_donation_id')
            }), 200
        else:
            return jsonify({'error': 'Failed to activate premium'}), 500
            
    except Exception as e:
        print(f"❌ Assignment error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/pending-payments', methods=['GET'])
def get_pending_payments():
    """Get all pending payments for admin review"""
    try:
        result = supabase.table('payments').select('*').eq('status', 'pending_assignment').order('created_at', desc=True).execute()
        
        payments = []
        for payment in result.data:
            webhook_data = payment.get('webhook_data', {})
            payments.append({
                'id': payment['id'],
                'amount_raw': payment.get('amount', 0),
                'amount_display': payment.get('amount_display', payment.get('amount', 0)),
                'package_type': payment['package_type'],
                'donator_name': webhook_data.get('donator_name', 'Anonymous'),
                'donator_email': webhook_data.get('donator_email', ''),
                'message': webhook_data.get('message', ''),
                'created_at': payment['created_at'],
                'saweria_donation_id': payment['saweria_donation_id'],
                'qr_string': payment.get('qr_string', ''),
                'donation_type': webhook_data.get('donation_type', 'donation')
            })
        
        return jsonify({
            'pending_payments': payments,
            'count': len(payments)
        }), 200
        
    except Exception as e:
        print(f"❌ Error getting pending payments: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'supabase_connected': supabase is not None
    }), 200

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5000))
    print(f"🚀 Saweria webhook server running on port {port}")
    app.run(host='0.0.0.0', port=port, debug=True)