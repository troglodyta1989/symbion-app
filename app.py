# app.py
from flask import Flask, render_template_string, request, jsonify, redirect
import stripe, os, sqlite3
from dotenv import load_dotenv

# Opcjonalny SendGrid
try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail
    SENDGRID_AVAILABLE = True
except:
    SENDGRID_AVAILABLE = False

load_dotenv()

STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
STRIPE_PUBLISHABLE_KEY = os.getenv('STRIPE_PUBLISHABLE_KEY')
STRIPE_PRICE_ID = os.getenv('STRIPE_PRICE_ID')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')
SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')
FROM_EMAIL = os.getenv('FROM_EMAIL')
BASE_URL = os.getenv('BASE_URL', 'http://localhost:4242')

if not STRIPE_SECRET_KEY or not STRIPE_PUBLISHABLE_KEY or not STRIPE_PRICE_ID:
    raise RuntimeError('W .env ustaw STRIPE_SECRET_KEY, STRIPE_PUBLISHABLE_KEY i STRIPE_PRICE_ID')

stripe.api_key = STRIPE_SECRET_KEY

app = Flask(__name__)
DB = 'symbion_subs.db'

# HTML czarno-biały front
INDEX_HTML = """
<!doctype html>
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Symbion — Subskrypcja</title>
<style>
body{background:#000;color:#eee;font-family:Inter,Arial;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
.card{background:#111;padding:28px;border-radius:12px;box-shadow:0 6px 30px rgba(0,0,0,.6);width:360px;text-align:center}
h1{margin:0 0 12px;font-size:20px}
p{margin:8px 0 18px;color:#ccc}
button{background:#fff;color:#000;padding:12px 18px;border-radius:8px;border:0;font-weight:700;cursor:pointer}
.muted{color:#888;font-size:13px;margin-top:12px}
.small{font-size:13px;color:#bbb;margin-top:8px}
a{color:#fff}
</style>
<script src="https://js.stripe.com/v3/"></script>
</head>
<body>
<div class="card">
<h1>Symbion — dostęp premium</h1>
<p>Pełen zestaw technik — 29.99 PLN / miesiąc</p>
<button id="subscribe">Subskrybuj 29,99 PLN / mies.</button>
<div class="small">7 dni trial. Możesz użyć kodu promocyjnego przy płatności.</div>
<div class="muted">Bezpieczne płatności obsługiwane przez Stripe</div>
<div style="margin-top:10px"><a href="/my-subscriptions">Moje subskrypcje / Panel płatności</a></div>
</div>
<script>
const stripe = Stripe("{{ publishable_key }}");
document.getElementById('subscribe').addEventListener('click', async () => {
  const res = await fetch('/create-checkout-session', { method: 'POST' });
  const data = await res.json();
  if (data.sessionId) {
    const { error } = await stripe.redirectToCheckout({ sessionId: data.sessionId });
    if (error) alert(error.message);
  } else {
    alert('Błąd utworzenia sesji płatności');
  }
});
</script>
</body>
</html>
"""

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY,
        stripe_customer_id TEXT UNIQUE,
        email TEXT,
        subscription_id TEXT,
        status TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()

@app.route('/')
def index():
    return render_template_string(INDEX_HTML, publishable_key=STRIPE_PUBLISHABLE_KEY)

@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            mode='subscription',
            line_items=[{'price': STRIPE_PRICE_ID,'quantity':1}],
            subscription_data={'trial_period_days':7},
            allow_promotion_codes=True,
            success_url=BASE_URL + '/success?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=BASE_URL + '/cancel',
        )
        return jsonify({'sessionId': session.id})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/success')
def success(): return '<h2>Subskrypcja zakończona sukcesem. Sprawdź e-maila.</h2>'

@app.route('/cancel')
def cancel(): return '<h2>Subskrypcja anulowana.</h2>'

@app.route('/my-subscriptions')
def my_subscriptions():
    email = request.args.get('email')
    if not email:
        return '<p>Podaj swój email jako ?email=you@domain.com aby otworzyć panel płatności.</p>'
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('SELECT stripe_customer_id FROM customers WHERE email=?', (email,))
    row = c.fetchone()
    conn.close()
    if not row:
        return '<p>Nie znaleziono subskrypcji dla tego e-maila.</p>'
    stripe_customer_id = row[0]
    try:
        portal_session = stripe.billing_portal.Session.create(
            customer=stripe_customer_id,
            return_url=BASE_URL
        )
        return redirect(portal_session.url)
    except Exception as e:
        return f'<p>Błąd tworzenia panelu: {e}</p>'

@app.route('/webhook', methods=['POST'])
def webhook():
    payload = request.data
    sig_header = request.headers.get('Stripe-Signature', None)
    event = None
    try:
        if STRIPE_WEBHOOK_SECRET:
            event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        else:
            event = stripe.Event.construct_from(request.get_json(), stripe.api_key)
    except:
        return 'Invalid webhook', 400

    ev_type = event['type']

    if ev_type == 'checkout.session.completed':
        session = event['data']['object']
        stripe_customer_id = session.get('customer')
        customer_email = session.get('customer_details', {}).get('email')
        subscription_id = session.get('subscription')
        save_customer(stripe_customer_id, customer_email, subscription_id, 'active')
        send_confirmation_email(customer_email, subscription_id)

    if ev_type == 'invoice.payment_failed':
        invoice = event['data']['object']
        mark_subscription_status(invoice.get('subscription'), 'past_due')

    if ev_type == 'customer.subscription.deleted':
        mark_subscription_status(event['data']['object'].get('id'), 'canceled')

    return '', 200

def save_customer(stripe_customer_id, email, subscription_id, status):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''INSERT OR IGNORE INTO customers (stripe_customer_id,email,subscription_id,status) VALUES (?,?,?,?)''',
              (stripe_customer_id,email,subscription_id,status))
    c.execute('''UPDATE customers SET subscription_id=?,status=?,email=? WHERE stripe_customer_id=?''',
              (subscription_id,status,email,stripe_customer_id))
    conn.commit()
    conn.close()

def mark_subscription_status(subscription_id,status):
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('UPDATE customers SET status=? WHERE subscription_id=?', (status,subscription_id))
    conn.commit()
    conn.close()

def send_confirmation_email(to_email,subscription_id):
    if not SENDGRID_AVAILABLE or not SENDGRID_API_KEY or not FROM_EMAIL:
        print('SendGrid nie skonfigurowany — pomijam wysyłkę e-maila')
        return
    message = Mail(
        from_email=FROM_EMAIL,
        to_emails=to_email,
        subject='Symbion — potwierdzenie subskrypcji',
        html_content=f'<p>Dzięki za subskrypcję. Twoje ID subskrypcji: {subscription_id}</p>'
    )
    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        resp = sg.send(message)
        print('Email wysłany:', resp.status_code)
    except Exception as e:
        print('Błąd wysyłki e-maila:', e)

if __name__ == '__main__':
    init_db()
    app.run(port=4242, debug=True)
