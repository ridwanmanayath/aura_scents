from django.urls import path
from . import views



urlpatterns = [
    path('', views.admin_login, name='admin_login'),
    path('dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('logout/', views.admin_logout, name='admin_logout'),

    path('users/', views.user_list, name='user_list'),
    path('users/<int:user_id>/toggle/', views.toggle_block_user, name='toggle_block_user'),

    path('categories/', views.category_list, name='category_list'),
    path('categories/add/', views.category_add, name='category_add'),

    path('categories/<int:category_id>/edit/', views.category_edit, name='category_edit'),
    path('categories/<int:category_id>/delete/', views.category_delete, name='category_delete'),

    path('products/', views.product_list, name='product_list'),
    path('products/add/', views.product_manage, name='product_add'),

    path('products/<int:product_id>/edit/', views.product_manage, name='product_edit'),
    path('products/<int:product_id>/delete/', views.product_delete, name='product_delete'),

    path('orders/', views.order_list, name='order_list'),
    path('order-detail/<int:order_id>/', views.order_detail, name='order_details'),
    path('orders/<int:order_id>/update-status/', views.update_order_status, name='update_order_status'),

    path('coupons/', views.manage_coupons, name='manage_coupons'),
    path('coupon-delete/<int:coupon_id>/', views.delete_coupon, name='delete_coupon'),


    path('offers/', views.manage_offers, name='manage_offers'),
    path('offers/<int:offer_id>/delete/', views.delete_offer, name='delete_offer'),

    path('sales-report/', views.sales_report, name='sales_report'),

    
    
]