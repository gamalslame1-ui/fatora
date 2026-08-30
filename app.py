from flask import Flask, render_template, request, redirect, url_for, flash, make_response
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'fatora-secret-key-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///fatora.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Database Models
class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100))
    phone = db.Column(db.String(20))
    address = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    invoices = db.relationship('Invoice', backref='client', lazy=True)

class Invoice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(50), unique=True, nullable=False)
    client_id = db.Column(db.Integer, db.ForeignKey('client.id'), nullable=False)
    issue_date = db.Column(db.Date, default=datetime.utcnow)
    due_date = db.Column(db.Date)
    status = db.Column(db.String(20), default='unpaid')  # unpaid, paid, overdue
    notes = db.Column(db.Text)
    subtotal = db.Column(db.Float, default=0)
    tax_rate = db.Column(db.Float, default=0)
    tax_amount = db.Column(db.Float, default=0)
    total = db.Column(db.Float, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship('InvoiceItem', backref='invoice', lazy=True, cascade='all, delete-orphan')

class InvoiceItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey('invoice.id'), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Float, default=1)
    unit_price = db.Column(db.Float, default=0)
    total = db.Column(db.Float, default=0)

# Routes
@app.route('/')
def index():
    invoices = Invoice.query.order_by(Invoice.created_at.desc()).all()
    clients = Client.query.all()
    stats = {
        'total_invoices': len(invoices),
        'paid': sum(1 for i in invoices if i.status == 'paid'),
        'unpaid': sum(1 for i in invoices if i.status == 'unpaid'),
        'overdue': sum(1 for i in invoices if i.status == 'overdue'),
        'total_revenue': sum(i.total for i in invoices if i.status == 'paid')
    }
    return render_template('index.html', invoices=invoices, clients=clients, stats=stats)

@app.route('/invoice/new', methods=['GET', 'POST'])
def new_invoice():
    if request.method == 'POST':
        client_id = request.form['client_id']
        if client_id == 'new':
            client = Client(
                name=request.form['client_name'],
                email=request.form['client_email'],
                phone=request.form['client_phone'],
                address=request.form['client_address']
            )
            db.session.add(client)
            db.session.flush()
            client_id = client.id

        invoice = Invoice(
            invoice_number=request.form['invoice_number'],
            client_id=client_id,
            due_date=datetime.strptime(request.form['due_date'], '%Y-%m-%d') if request.form['due_date'] else None,
            notes=request.form.get('notes', ''),
            tax_rate=float(request.form.get('tax_rate', 0))
        )
        db.session.add(invoice)
        db.session.flush()

        # Add items
        descriptions = request.form.getlist('item_description[]')
        quantities = request.form.getlist('item_quantity[]')
        prices = request.form.getlist('item_price[]')

        subtotal = 0
        for desc, qty, price in zip(descriptions, quantities, prices):
            if desc.strip():
                qty = float(qty) if qty else 1
                price = float(price) if price else 0
                item_total = qty * price
                item = InvoiceItem(
                    invoice_id=invoice.id,
                    description=desc,
                    quantity=qty,
                    unit_price=price,
                    total=item_total
                )
                db.session.add(item)
                subtotal += item_total

        invoice.subtotal = subtotal
        invoice.tax_amount = subtotal * (invoice.tax_rate / 100)
        invoice.total = subtotal + invoice.tax_amount

        db.session.commit()
        flash('تم إنشاء الفاتورة بنجاح!', 'success')
        return redirect(url_for('view_invoice', id=invoice.id))

    clients = Client.query.all()
    next_number = f"INV-{datetime.now().year}-{Invoice.query.count() + 1:04d}"
    return render_template('invoice_form.html', clients=clients, invoice=None, next_number=next_number)

@app.route('/invoice/<int:id>')
def view_invoice(id):
    invoice = Invoice.query.get_or_404(id)
    return render_template('view_invoice.html', invoice=invoice)

@app.route('/invoice/<int:id>/edit', methods=['GET', 'POST'])
def edit_invoice(id):
    invoice = Invoice.query.get_or_404(id)
    if request.method == 'POST':
        invoice.notes = request.form.get('notes', '')
        invoice.tax_rate = float(request.form.get('tax_rate', 0))
        invoice.due_date = datetime.strptime(request.form['due_date'], '%Y-%m-%d') if request.form['due_date'] else None

        # Delete old items
        InvoiceItem.query.filter_by(invoice_id=invoice.id).delete()

        # Add new items
        descriptions = request.form.getlist('item_description[]')
        quantities = request.form.getlist('item_quantity[]')
        prices = request.form.getlist('item_price[]')

        subtotal = 0
        for desc, qty, price in zip(descriptions, quantities, prices):
            if desc.strip():
                qty = float(qty) if qty else 1
                price = float(price) if price else 0
                item_total = qty * price
                item = InvoiceItem(
                    invoice_id=invoice.id,
                    description=desc,
                    quantity=qty,
                    unit_price=price,
                    total=item_total
                )
                db.session.add(item)
                subtotal += item_total

        invoice.subtotal = subtotal
        invoice.tax_amount = subtotal * (invoice.tax_rate / 100)
        invoice.total = subtotal + invoice.tax_amount

        db.session.commit()
        flash('تم تحديث الفاتورة بنجاح!', 'success')
        return redirect(url_for('view_invoice', id=invoice.id))

    clients = Client.query.all()
    return render_template('invoice_form.html', clients=clients, invoice=invoice)

@app.route('/invoice/<int:id>/status', methods=['POST'])
def update_status(id):
    invoice = Invoice.query.get_or_404(id)
    invoice.status = request.form['status']
    db.session.commit()
    flash('تم تحديث الحالة!', 'success')
    return redirect(url_for('view_invoice', id=invoice.id))

@app.route('/invoice/<int:id>/delete', methods=['POST'])
def delete_invoice(id):
    invoice = Invoice.query.get_or_404(id)
    db.session.delete(invoice)
    db.session.commit()
    flash('تم حذف الفاتورة!', 'success')
    return redirect(url_for('index'))

@app.route('/clients')
def clients():
    clients = Client.query.all()
    return render_template('clients.html', clients=clients)

@app.route('/client/<int:id>')
def client_detail(id):
    client = Client.query.get_or_404(id)
    return render_template('client_detail.html', client=client)

with app.app_context():
    db.create_all()

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

