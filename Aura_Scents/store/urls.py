from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_page, name='home_page'),
    path('products', views.products_page, name='products_page'),
    path('product/<int:product_id>/', views.product_detail_view, name='product_detail'),
    
    path('toggle-wishlist/<int:product_id>/', views.toggle_wishlist, name='toggle_wishlist'),
    path('toggle-wishlist/<int:product_id>/<int:variant_id>/', views.toggle_wishlist, name='toggle_wishlist_with_variant'),
    path('wishlist/', views.wishlist, name='wish_list'),

    path('register/', views.user_register, name='register_page'),
    path('otp-verify/<int:user_id>/', views.otp_verify, name='otp_verify'),
    path('otp-resend/<int:user_id>/', views.otp_resend, name='otp_resend'),
    path('login/', views.user_login, name='login_page'),
    path('logout/', views.user_logout, name='logout_page'),


    path('profile/', views.profile_view, name='profile'),
    path('profile/edit/', views.profile_edit, name='profile_edit'),

    path('verify-password/', views.verify_password, name='verify_password'),
    path('change-password/', views.change_password, name='change_password'),

    path('address/', views.address_list, name='address_list'),
    path('address/add/', views.address_add, name='address_add'),
    path('address/<int:pk>/edit/', views.address_edit, name='address_edit'),
    path('address/<int:pk>/delete/', views.address_delete, name='address_delete'),


    path('cart/', views.cart_view, name='cart'),
    path('add-to-cart/<int:product_id>/', views.add_to_cart, name='add_to_cart'),
    path('update-cart/<int:item_id>/', views.update_cart, name='update_cart'),  
    path('remove-from-cart/<int:item_id>/', views.remove_from_cart, name='remove_from_cart'),  
    path('clear-cart/', views.clear_cart, name='clear_cart'),

    path('checkout/', views.checkout, name='checkout'),
    path('order-success/<int:order_id>/', views.order_success, name='order_success'),


    path('orders/', views.order_list, name='orders'),
    path('order-detail/<str:order_id>/', views.order_detail, name='order_detail'),
    path('order-detail/<str:order_id>/invoice/', views.download_invoice, name='download_invoice'),
    path('cancel/<str:order_id>/', views.cancel_order, name='cancel_order'),
    path('return/<str:order_id>/', views.return_order, name='return_order'),

     # Email update URLs
    path('check-email-availability/', views.check_email_availability, name='check_email_availability'),
    path('verify-email-otp/', views.verify_email_otp, name='verify_email_otp'),
    path('resend-email-otp/', views.resend_email_otp, name='resend_email_otp'),

    path('payment-handler/', views.payment_handler, name='payment_handler'),
    path('order-failed/<str:message>/', views.order_failed, name='order_failed'),

    path('payment-init/<int:order_id>/', views.payment_handler_init, name='payment_handler_init'),
    
    

    
    

    

]
