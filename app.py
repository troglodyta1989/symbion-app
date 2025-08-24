from flask import Flask, request, jsonify
import stripe
import os

app = Flask(__name__)

stripe.api_key = os.getenv('STRIPE_SECRET_KEY')

@app.route('/')
def index():
    return jsonify({'status': 'ok', 'message': 'Symbion działa!'})

@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'product_data': {'name': 'Symbion Premium'},
                    'unit_amount': 1000,
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url='https://your-render-url.com/success',
            cancel_url='https://your-render-url.com/cancel',
        )
        return jsonify({'id': session.id})
    except Exception as e:
        return jsonify(error=str(e)), 403

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
