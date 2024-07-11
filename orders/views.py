    #*====================  ALL IMPORTS ======================== # 

from django.shortcuts import render, redirect
from carts.models import CartItem
from paypal.standard.forms import PayPalPaymentsForm
from django.conf import settings
import uuid
from django.urls import reverse
from .forms import OrderForm
import datetime
from .models import Order, Payment, OrderProduct
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse
from paypal.standard.models import ST_PP_COMPLETED
import logging
from store.models import Product
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from accounts.models import Account



    #*====================  STEP 1 FUNCTION  ======================== # 

def payment_product(request):
  
    current_user = request.user

    cart_items = CartItem.objects.filter(user=current_user)
    cart_count = cart_items.count()
    if cart_count <= 0:
        return redirect('store')
    
    total=0
    quantity=0
    grand_total = 0
    tax = 0
    for cart_item in cart_items:
        total += (cart_item.product.price * cart_item.quantity)
        quantity += cart_item.quantity
    tax = (2 * total) / 100
    grand_total = total + tax

    host = request.get_host()

   
    if request.method == 'POST':
        form = OrderForm(request.POST)
        if form.is_valid():
            data = Order()
            data.user = current_user
            data.first_name = form.cleaned_data['first_name']
            data.last_name = form.cleaned_data['last_name']
            data.phone = form.cleaned_data['phone']
            data.email = form.cleaned_data['email']
            data.address_line_1 = form.cleaned_data['address_line_1']
            data.address_line_2 = form.cleaned_data['address_line_2']
            data.country = form.cleaned_data['country']
            data.state = form.cleaned_data['state']
            data.city = form.cleaned_data['city']
            data.order_note = form.cleaned_data['order_note']
            data.order_total = grand_total
            data.tax = tax
            data.ip = request.META.get('REMOTE_ADDR')
            data.save()

            yr = int(datetime.date.today().strftime('%Y'))
            dt = int(datetime.date.today().strftime('%d'))
            mt = int(datetime.date.today().strftime('%m'))
            d = datetime.date(yr, mt, dt)
            current_date = d.strftime("%Y%m%d")
            order_number = current_date + str(data.id)
            data.order_number = order_number
            data.save()

            order = Order.objects.get(user=current_user, is_ordered=False, order_number=order_number)
            # Generate item names from cart items
            item_names = [item.product.product_name for item in cart_items]
            item_name_str = ', '.join(item_names)

    paypal_checkout = {
        'business': settings.PAYPAL_RECEIVER_EMAIL,
        'custom':current_user, 
        'amount': grand_total,
        'item_name': item_name_str,
        'invoice': str(uuid.uuid4()),  # Ensure this is a string
        'currency_code': 'USD',
        "item_number":order_number,
        'notify_url': f"https://89b4-49-43-201-233.ngrok-free.app{reverse('paypal-ipn')}",
        'return_url': f"http://{host}{reverse('payment-success',kwargs = {'order_number':order_number})}",
        'cancel_url': f"http://{host}{reverse('payment-failed')}",
    }
    paypal_payment = PayPalPaymentsForm(initial=paypal_checkout)

    context = {
        'order': order,
        'cart_items': cart_items,
        'total': total,
        'tax': tax,
        'grand_total': grand_total,
        'paypal': paypal_payment
    }

    return render(request, 'orders/payments.html', context)


    #*====================  STEP 2 FUNCTION  ======================== # 

def PaymentSuccessful(request,order_number):
    print(order_number)
    try:
        order = Order.objects.get(order_number=order_number, is_ordered=True)
        ordered_products = OrderProduct.objects.filter(order_id=order.id)
        payment = order.payment  # Directly access the payment field of the order

        subtotal = 0
        for i in ordered_products:
            subtotal += i.product_price * i.quantity

        context = {
            'order': order,
            'ordered_products': ordered_products,
            'order_number': order.order_number,
            'transID': payment.payment_id if payment else None,
            'payment': payment,
            'subtotal': subtotal,
        }
        return render(request, 'orders/order_complete.html', context)
    except (Payment.DoesNotExist, Order.DoesNotExist):
        return redirect('home')
  

    #*====================  STEP 3 FUNCTION  ======================== # 

def paymentFailed(request):

    product = "All Items"

    return render(request, 'store/payment-failed.html', {'product': product})






    #*====================  STEP 4 FUNCTION  ======================== # 

logger = logging.getLogger(__name__)
@csrf_exempt
def paypal_ipn(request):
    ipn_data = request.POST

    # Ensure the payment_status is completed
    if ipn_data.get('payment_status') == ST_PP_COMPLETED:
        try:
            # Extract necessary IPN data
            transaction_id = ipn_data.get('txn_id')
            order_number = ipn_data.get('item_number')  
            status = ipn_data.get('payment_status')
            current_user = ipn_data.get('custom')



            user = Account.objects.get(email=current_user)
            order = Order.objects.get(user=user.id, is_ordered=False, order_number=order_number)
            if order:
                # Store transaction details inside Payment model
                payment = Payment(
                    user=user,
                    payment_id=transaction_id,
                    payment_method='Paypal',
                    amount_paid=order.order_total,
                    status=status,
                )
                payment.save()
                order.payment = payment
                order.is_ordered = True
                order.save()

                cart_items = CartItem.objects.filter(user=user)

                for item in cart_items:
                    orderproduct = OrderProduct()
                    orderproduct.order_id = order.id
                    orderproduct.payment = payment
                    orderproduct.user_id = user.id
                    orderproduct.product_id = item.product_id
                    orderproduct.quantity = item.quantity
                    orderproduct.product_price = item.product.price
                    orderproduct.ordered = True
                    orderproduct.save()

                    cart_item = CartItem.objects.get(id=item.id)
                    product_variation = cart_item.variations.all()
                    orderproduct = OrderProduct.objects.get(id=orderproduct.id)
                    orderproduct.variations.set(product_variation)
                    orderproduct.save()

                    # Reduce the quantity of the sold products
                    product = Product.objects.get(id=item.product_id)
                    product.stock -= item.quantity
                    product.save()

                # Clear cart
                CartItem.objects.filter(user=user).delete()

                # Send order received email to customer
                mail_subject = 'Thank you for your order!'
                message = render_to_string('orders/order_received_email.html', {
                    'user': user,
                    'order': order,
                })
                to_email = user.email
                send_email = EmailMessage(mail_subject, message, to=[to_email])
                send_email.send()
                return HttpResponse("OK")
            else:
                logger.error(f"Order with order number {order_number} not found.")
        except Exception as e:
            logger.error(f"Error processing IPN: {str(e)}")
    else:
        logger.warning(f"Payment not completed. Status: {ipn_data.get('payment_status')}")
    print("Eveything done successfully") 
    return HttpResponse("OK")