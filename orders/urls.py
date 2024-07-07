from django.urls import path
from . import views

urlpatterns = [ 
    path('payment_product/', views.payment_product, name='payment-product'),
    path('payment-success/<int:order_number>/', views.PaymentSuccessful, name='payment-success'),
    path('payment-failed/', views.paymentFailed, name='payment-failed'),
    path('paypal-ipn/', views.paypal_ipn, name='paypal-ipn'),
]