from django.shortcuts import render, redirect, get_object_or_404
from back_office.models import *
from django.core.paginator import Paginator
from django.db.models import Q,Prefetch

from django.contrib import messages

from django.http import Http404

from .forms import RegistrationForm,LoginForm
from .models import *

import random

from django.core.mail import send_mail
from django.conf import settings

from django.contrib.auth import authenticate, login,logout

from django.contrib.auth.decorators import login_required
from .forms import UserProfileForm, AddressForm
from .models import Address

from django.views.decorators.http import require_POST

from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json

from decimal import Decimal,ROUND_HALF_UP

from django.template.loader import render_to_string

from django.contrib.auth.hashers import check_password
from django.contrib.auth import authenticate, update_session_auth_hash

from django.views.decorators.http import require_http_methods

import os

from django.utils import timezone

#Download Invoice
from django.shortcuts import get_object_or_404
from .models import Order
from .utils import render_to_pdf
from django.http import HttpResponse, HttpResponseForbidden

from .utils import *
from django.urls import reverse
from razorpay.errors import SignatureVerificationError

from django.db import transaction



def home_page(request):
    # Get latest products with prefetch_related for efficiency
    latest_products = Product.objects.filter(
        is_deleted=False,
        is_blocked=False
    ).prefetch_related('variants').order_by('-created_at')[:4]
    
    # Add display_price to each product
    for product in latest_products:
        # Get active variants (not deleted and not blocked)
        active_variants = product.variants.filter(
            is_deleted=False,
            is_blocked=False
        ).order_by('created_at')
        
        if active_variants.exists():
            # If product has variants, use the first variant's price
            product.display_price = active_variants.first().price
        else:
            # If no variants, use the base product price
            product.display_price = product.price
    
    return render(request, 'store/home_page.html', { 
        'latest_products': latest_products 
    })


def products_page(request):
    # Base queryset with prefetch for variants, images, and offers
    products = Product.objects.filter(
        is_blocked=False,
        is_deleted=False
    ).prefetch_related(
        Prefetch(
            'variants',
            queryset=ProductVariant.objects.filter(
                is_deleted=False,
                is_blocked=False
            ).order_by('created_at')
        ),
        'images',
        Prefetch(
            'offers',
            queryset=ProductOffer.objects.select_related('offer')
        ),
        Prefetch(
            'category__offers',
            queryset=CategoryOffer.objects.select_related('offer')
        )
    )

    categories = Category.objects.filter(is_deleted=False, is_blocked=False)

    # --- Search ---
    query = request.GET.get('q', '')
    if query:
        products = products.filter(Q(name__icontains=query) | Q(description__icontains=query))

    # --- Filter by Category ---
    category_id = request.GET.get('category')
    if category_id and category_id.isdigit():
        products = products.filter(category_id=int(category_id))

    # Convert to list to add display_price and offer attributes
    products_list = list(products)

    # Add display_price and offer details to each product
    for product in products_list:
        # Get base price (from variant or product)
        first_variant = product.variants.first()
        product.display_price = first_variant.price if first_variant else product.price
        
        # Get best offer and calculate discounted price
        best_offer = get_best_offer_for_product(product)
        product.best_offer = best_offer
        if best_offer and best_offer.is_valid():
            discount_multiplier = Decimal('1.0') - (best_offer.discount_percentage / Decimal('100.0'))
            product.discounted_price = product.display_price * discount_multiplier
            product.discount_percentage = best_offer.discount_percentage
            product.offer_type = best_offer.offer_type
        else:
            product.discounted_price = None
            product.discount_percentage = None
            product.offer_type = None

    # --- Filter by Price Range (Radio Button) ---
    price_range = request.GET.get('price_range', '')
    min_price, max_price = None, None

    if price_range:
        if '-' in price_range:
            parts = price_range.split('-')
            if parts[0]:
                min_price = parts[0]
                # Filter by discounted_price if available, else display_price
                products_list = [
                    p for p in products_list 
                    if (p.discounted_price or p.display_price) >= float(min_price)
                ]
            if len(parts) > 1 and parts[1]:
                max_price = parts[1]
                # Filter by discounted_price if available, else display_price
                products_list = [
                    p for p in products_list 
                    if (p.discounted_price or p.display_price) <= float(max_price)
                ]

    # --- Sorting ---
    sort_by = request.GET.get('sort')
    if sort_by == 'price_asc':
        products_list.sort(key=lambda x: x.discounted_price or x.display_price)
    elif sort_by == 'price_desc':
        products_list.sort(key=lambda x: x.discounted_price or x.display_price, reverse=True)
    elif sort_by == 'name_asc':
        products_list.sort(key=lambda x: x.name)
    elif sort_by == 'name_desc':
        products_list.sort(key=lambda x: x.name, reverse=True)

    # --- Pagination ---
    paginator = Paginator(products_list, 5)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # --- Wishlist ---
    wishlist_product_ids = []
    if request.user.is_authenticated:
        wishlist_product_ids = WishlistItem.objects.filter(user=request.user).values_list('product_id', flat=True)

    context = {
        'products': page_obj,
        'categories': categories,
        'query': query,
        'sort': sort_by,
        'category_id': category_id,
        'min_price': min_price,
        'max_price': max_price,
        'page_obj': page_obj,
        'wishlist_product_ids': wishlist_product_ids,
    }
    return render(request, 'store/products_page.html', context)

def product_detail_view(request, product_id):
    try:
        product = Product.objects.prefetch_related('images', 'variants').get(pk=product_id)
    except Product.DoesNotExist:
        messages.error(request, "Product not found.")
        return redirect('products_page')

    # Redirect if blocked, deleted, or category is blocked
    if product.is_blocked or product.is_deleted or product.category.is_blocked:
        messages.warning(request, "This product is not available.")
        return redirect('products_page')

    # Get available variants (not blocked or deleted)
    available_variants = product.variants.filter(is_blocked=False, is_deleted=False).order_by('volume')

    # Determine default variant and stock status
    default_variant = None
    if available_variants.exists():
        default_variant = available_variants.first()
        current_stock = default_variant.stock
        current_price = default_variant.price
    else:
        current_stock = product.stock
        current_price = product.price

    # Stock status
    if current_stock == 0:
        stock_status = "Out of Stock"
    else:
        stock_status = f"In Stock: {current_stock}"

    # Get best offer for the product
    best_offer = get_best_offer_for_product(product)
    original_price = current_price
    discounted_price = current_price
    if best_offer:
        discounted_price = current_price * (Decimal('1.0') - (best_offer.discount_percentage / Decimal('100.0')))

    # Calculate discounted prices for all variants
    variant_data = []
    for variant in available_variants:
        variant_discounted_price = variant.price
        if best_offer:
            variant_discounted_price = variant.price * (Decimal('1.0') - (best_offer.discount_percentage / Decimal('100.0')))
        variant_data.append({
            'variant': variant,
            'original_price': variant.price,
            'discounted_price': variant_discounted_price
        })

    # Related products with discounted prices
    related_products = (
        Product.objects
        .filter(category=product.category, is_blocked=False, is_deleted=False)
        .exclude(id=product.id)[:4]
    )
    related_products_data = []
    for related in related_products:
        related_best_offer = get_best_offer_for_product(related)
        related_original_price = related.price
        related_discounted_price = related.price
        if related_best_offer:
            related_discounted_price = related.price * (Decimal('1.0') - (related_best_offer.discount_percentage / Decimal('100.0')))
        related_products_data.append({
            'product': related,
            'original_price': related_original_price,
            'discounted_price': related_discounted_price,
            'best_offer': related_best_offer
        })

    # Check if product is already in user's wishlist
    in_wishlist = False
    if request.user.is_authenticated:
        in_wishlist = WishlistItem.objects.filter(user=request.user, product=product).exists()

    context = {
        'product': product,
        'available_variants': variant_data,
        'default_variant': default_variant,
        'current_price': current_price,
        'original_price': original_price,
        'discounted_price': discounted_price,
        'best_offer': best_offer,
        'current_stock': current_stock,
        'breadcrumbs': [product.category.name, product.name],
        'stock_status': stock_status,
        'related_products': related_products_data,
        'in_wishlist': in_wishlist,
    }

    return render(request, 'store/product_detail_page.html', context)

@require_POST
@csrf_exempt
@login_required
def toggle_wishlist(request, product_id, variant_id=None):
    product = get_object_or_404(Product, id=product_id)
    variant = get_object_or_404(ProductVariant, id=variant_id) if variant_id else None

    # Check if the wishlist item already exists for this product and variant combination
    wishlist_item, created = WishlistItem.objects.get_or_create(
        user=request.user,
        product=product,
        variant=variant,
        defaults={'added_at': timezone.now()}
    )

    if not created:
        # Item exists → remove it
        wishlist_item.delete()
        message = 'Removed from wishlist'
        status = 'success'
    else:
        # Item didn't exist → added
        message = 'Added to wishlist'
        status = 'success'

    # Handle AJAX request
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({
            'status': status,
            'message': message,
            'variant_id': variant_id
        })

    # Fallback for non-AJAX request
    return redirect('wish_list')

@login_required
def wishlist(request):
    wishlist_items = WishlistItem.objects.filter(user=request.user).select_related('product', 'variant')
    wishlist_data = []
    for item in wishlist_items:
        if item.product.is_blocked or item.product.is_deleted or (item.variant and (item.variant.is_blocked or item.variant.is_deleted)):
            continue

        # Get price (variant price if exists, else product price)
        original_price = item.variant.price if item.variant else item.product.price

        # Get best offer for the product
        best_offer = get_best_offer_for_product(item.product)
        discounted_price = original_price
        if best_offer:
            discounted_price = original_price * (Decimal('1.0') - (best_offer.discount_percentage / Decimal('100.0')))

        wishlist_data.append({
            'product': item.product,
            'variant': item.variant,
            'original_price': original_price,
            'discounted_price': discounted_price,
            'best_offer': best_offer,
            'display_name': item.get_display_name()
        })

    context = {
        'wishlist_data': wishlist_data,
    }
    return render(request, 'store/wishlist.html', context)


def send_otp_email(user, otp_code):
    subject = "Your OTP Code"
    message = f"Your OTP code is {otp_code}. It is valid for 5 minutes."
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email])


def user_register(request):
    if request.user.is_authenticated:
        return redirect('home_page')
    
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False  # Inactive until OTP is verified
            user.save()

            otp_code = str(random.randint(100000, 999999))
            OTP.objects.create(user=user, otp_code=otp_code)
            send_otp_email(user, otp_code)
            return redirect('otp_verify', user_id=user.id)
    else:
        form = RegistrationForm()
    return render(request, 'store/register_page.html', {'form': form})


def otp_verify(request, user_id):
    user = User.objects.get(id=user_id)
    if request.method == 'POST':
        entered_otp = request.POST.get('otp')
        otp_instance = OTP.objects.filter(user=user, is_verified=False).last()
        if otp_instance and not otp_instance.is_expired():
            if otp_instance.otp_code == entered_otp:
                otp_instance.is_verified = True
                otp_instance.save()
                user.is_active = True
                user.save()
                messages.success(request, "Account verified successfully.")
                return redirect('login_page')
            else:
                messages.error(request, "Invalid OTP")
        else:
            messages.error(request, "OTP expired or invalid.")
    return render(request, 'store/otp_verify.html', {'user': user})

def otp_resend(request, user_id):
    user = User.objects.get(id=user_id)
    otp_code = str(random.randint(100000, 999999))
    OTP.objects.create(user=user, otp_code=otp_code)
    send_otp_email(user, otp_code)
    messages.info(request, "New OTP sent.")
    return redirect('otp_verify', user_id=user.id)

def user_login(request):
    if request.user.is_authenticated:
        return redirect('home_page')

    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password']
            user = authenticate(request, email=email, password=password)
            if user:
                if user.is_blocked:
                    messages.error(request, "Account is blocked.")
                elif not user.is_active:
                    messages.error(request, "Account not verified.")
                    return redirect('verify_otp', user_id=user.id)
                else:
                    login(request, user)
                    return redirect('home_page')
            else:
                messages.error(request, "Invalid credentials.")
    else:
        form = LoginForm()
    return render(request, 'store/login_page.html', {'form': form})
    

def user_logout(request):
    logout(request)
    return redirect('home_page')


@login_required
def profile_view(request):
    user = request.user
    # Assuming each user has one address for simplicity. Adjust if it's many.
    address = Address.objects.filter(user=user).first()
    return render(request, 'store/profile.html', {
        'user': user,
        'address': address,
    })

# Edit Profile View - Fixed
@login_required
def profile_edit(request):
    user = request.user
    address = Address.objects.filter(user=user).first()

    if request.method == 'POST':
        # Handle image deletion
        if 'delete_image' in request.POST:
            if user.profile_image:
                # Delete the file from storage
                if os.path.exists(user.profile_image.path):
                    os.remove(user.profile_image.path)
                # Clear the field
                user.profile_image = None
                user.save()
                messages.success(request, 'Profile image deleted successfully.')
            return redirect('profile_edit')  
        
        # Handle regular form submission
        user_form = UserProfileForm(request.POST, request.FILES, instance=user)
        address_form = AddressForm(request.POST, instance=address)

        if user_form.is_valid() and address_form.is_valid():
            try:
                user_form.save()
                address_instance = address_form.save(commit=False)
                address_instance.user = user
                address_instance.save()
                # messages.success(request, 'Profile updated successfully!')
                return redirect('profile')  
            except Exception as e:
                messages.error(request, f'An error occurred while saving: {str(e)}')
        else:
            # Add form errors to messages
            for field, errors in user_form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
            for field, errors in address_form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        user_form = UserProfileForm(instance=user)
        address_form = AddressForm(instance=address)

    return render(request, 'store/profile_edit.html', {
        'user_form': user_form,
        'address_form': address_form,
    })

@login_required
def verify_password(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        current_password = data.get('current_password')
        
        # Check if the current password is correct
        if check_password(current_password, request.user.password):
            return JsonResponse({'success': True, 'message': 'Password Verified'})
        else:
            return JsonResponse({'success': False, 'message': 'Password Incorrect'})
    
    return JsonResponse({'success': False, 'message': 'Invalid request'})

@login_required
def change_password(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        current_password = data.get('current_password')
        new_password = data.get('new_password')
        confirm_password = data.get('confirm_password')
        
        # Verify current password
        if not check_password(current_password, request.user.password):
            return JsonResponse({'success': False, 'message': 'Current password is incorrect'})
        
        # Check if new passwords match
        if new_password != confirm_password:
            return JsonResponse({'success': False, 'message': 'New passwords do not match'})
        
        # Check password length
        if len(new_password) < 8:
            return JsonResponse({'success': False, 'message': 'Password must be at least 8 characters long'})
        
        # Update password
        request.user.set_password(new_password)
        request.user.save()
        
        # Keep user logged in after password change
        update_session_auth_hash(request, request.user)
        
        return JsonResponse({'success': True, 'message': 'Password changed successfully'})
    
    return JsonResponse({'success': False, 'message': 'Invalid request'})

@login_required
def address_list(request):
    addresses = request.user.addresses.all()
    return render(request, 'store/address_list.html', {'addresses': addresses})

# Add Address
@login_required
def address_add(request):
    if request.method == 'POST':
        form = AddressForm(request.POST)
        if form.is_valid():
            address = form.save(commit=False)
            address.user = request.user
            address.save()
            return redirect('address_list')
    else:
        form = AddressForm()
    return render(request, 'store/address_form.html', {
        'form': form,
        'title': 'Add New Address',
        'button_text': 'Save Address'
    })

# Edit Address

@login_required
def address_edit(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    if request.method == 'POST':
        form = AddressForm(request.POST, instance=address)
        if form.is_valid():
            form.save()
            return redirect('address_list')
    else:
        form = AddressForm(instance=address)
    return render(request, 'store/address_form.html', {
        'form': form,
        'title': 'Edit Address',
        'button_text': 'Update Address'
    })

# Delete Address
@require_POST
@login_required
def address_delete(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    address.delete()
    return redirect('address_list')

# Cart View
def cart_view(request):
    cart = None
    items = []
    cart_total = 0

    if request.user.is_authenticated:
        cart = Cart.objects.filter(user=request.user).first()
        if cart:
            items = cart.items.select_related('product', 'variant')
            cart_total = sum(item.subtotal() for item in items)

    context = {
        'cart': cart,
        'items': items,
        'cart_total': cart_total,
    }
    return render(request, 'store/cart.html', context)


# Add to Cart
MAX_QUANTITY = 10
@csrf_exempt
def add_to_cart(request, product_id):
    if not request.user.is_authenticated:
        return JsonResponse({'status': 'error', 'message': 'Login required'}, status=401)

    product = get_object_or_404(Product, id=product_id)

    # Check if product is available
    if product.is_blocked or product.is_deleted or product.category.is_blocked or product.category.is_deleted:
        return JsonResponse({'status': 'error', 'message': 'Product is unavailable'}, status=400)

    # Get variant if specified or use first available variant
    variant_id = request.POST.get('variant_id')
    variant = None
    
    # If product has variants but no variant was specified, use the first available variant
    if product.variants.exists() and not variant_id:
        variant = product.variants.filter(is_blocked=False, is_deleted=False).first()
        if not variant:
            return JsonResponse({'status': 'error', 'message': 'No available variants for this product'}, status=400)
    elif variant_id:
        try:
            variant = ProductVariant.objects.get(id=variant_id, product=product)
            if variant.is_blocked or variant.is_deleted:
                return JsonResponse({'status': 'error', 'message': 'Product variant is unavailable'}, status=400)
        except ProductVariant.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Invalid variant selected'}, status=400)

    # Check stock availability
    available_stock = variant.stock if variant else product.stock
    if available_stock == 0:
        return JsonResponse({'status': 'error', 'message': 'Out of stock'}, status=400)

    quantity = int(request.POST.get('quantity', 1))

    if quantity < 1:
        return JsonResponse({'status': 'error', 'message': 'Invalid quantity'}, status=400)

    if quantity > MAX_QUANTITY:
        return JsonResponse({'status': 'error', 'message': f'Maximum allowed quantity is {MAX_QUANTITY}'}, status=400)

    if quantity > available_stock:
        return JsonResponse({'status': 'error', 'message': 'Quantity exceeds available stock'}, status=400)

    # Get or create cart
    cart, _ = Cart.objects.get_or_create(user=request.user)

    # Get or create cart item with variant consideration
    cart_item, created = CartItem.objects.get_or_create(
        cart=cart,
        product=product,
        variant=variant,  
        defaults={'quantity': 0}
    )

    if not created:
        new_quantity = cart_item.quantity + quantity
        if new_quantity > available_stock or new_quantity > MAX_QUANTITY:
            return JsonResponse({'status': 'error', 'message': 'Quantity exceeds available stock or limit'}, status=400)
        cart_item.quantity = new_quantity
    else:
        cart_item.quantity = quantity

    cart_item.save()

    # Calculate updated cart quantity
    total_quantity = sum(item.quantity for item in cart.items.all())

    # Remove from wishlist if exists
    WishlistItem.objects.filter(user=request.user, product=product).delete()

    return JsonResponse({
        'status': 'success',
        'message': 'Added to cart',
        'cart_quantity': total_quantity,
        'item_price': str(variant.price if variant else product.price)
    })


@csrf_exempt
@login_required
@require_POST
def update_cart(request, item_id):
    try:
        # Parse JSON data if request is JSON, otherwise use POST data
        if request.content_type == 'application/json':
            data = json.loads(request.body)
            action = data.get('action')
        else:
            action = request.POST.get('action')
        
        # Get cart and cart item
        cart = Cart.objects.get(user=request.user)
        cart_item = CartItem.objects.get(id=item_id, cart=cart)
        
        # Check if product/variant is still available
        if cart_item.product.is_blocked or cart_item.product.is_deleted:
            return JsonResponse({'status': 'error', 'message': 'Product is no longer available'}, status=400)
        
        if cart_item.variant and (cart_item.variant.is_blocked or cart_item.variant.is_deleted):
            return JsonResponse({'status': 'error', 'message': 'Product variant is no longer available'}, status=400)
        
        available_stock = cart_item.get_stock()

        if action == 'increment':
            if cart_item.quantity >= available_stock:
                return JsonResponse({'status': 'error', 'message': 'Only limited stock available'})
            elif cart_item.quantity >= MAX_QUANTITY:
                return JsonResponse({'status': 'error', 'message': 'Maximum quantity per user reached'})
            else:
                cart_item.quantity += 1
                cart_item.save()
                return JsonResponse({
                    'status': 'success', 
                    'message': 'Quantity increased',
                    'new_quantity': cart_item.quantity,
                    'new_subtotal': float(cart_item.subtotal())
                })

        elif action == 'decrement':
            if cart_item.quantity > 1:
                cart_item.quantity -= 1
                cart_item.save()
                return JsonResponse({
                    'status': 'success', 
                    'message': 'Quantity decreased',
                    'new_quantity': cart_item.quantity,
                    'new_subtotal': float(cart_item.subtotal())
                })
            else:
                return JsonResponse({'status': 'error', 'message': 'Minimum quantity is 1'})

        return JsonResponse({'status': 'error', 'message': 'Invalid action'})
        
    except Cart.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Cart not found'}, status=404)
    except CartItem.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Cart item not found'}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON data'}, status=400)
    except Exception as e:
        print(f"Error in update_cart: {str(e)}")  # For debugging
        return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred'}, status=500)


@csrf_exempt
@login_required
@require_POST
def remove_from_cart(request, item_id):
    try:
        cart = Cart.objects.get(user=request.user)
        cart_item = CartItem.objects.get(id=item_id, cart=cart)
        cart_item.delete()
        return JsonResponse({'status': 'success', 'message': 'Removed from cart'})
    except Cart.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Cart not found'}, status=404)
    except CartItem.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Cart item not found'}, status=404)
    except Exception as e:
        print(f"Error in remove_from_cart: {str(e)}")  # For debugging
        return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred'}, status=500)


@csrf_exempt
@login_required
@require_POST
def clear_cart(request):
    try:
        cart = Cart.objects.filter(user=request.user).first()
        if cart:
            cart.items.all().delete()
            return JsonResponse({'status': 'success', 'message': 'Cart cleared successfully'})
        return JsonResponse({'status': 'error', 'message': 'Cart not found'})
    except Exception as e:
        print(f"Error in clear_cart: {str(e)}")  # For debugging
        return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred'}, status=500)


# def product_detail(request, product_id):
#     """Product detail view with variant support"""
#     product = get_object_or_404(Product, id=product_id)
    
#     # Get available variants (not blocked/deleted)
#     available_variants = product.variants.filter(
#         is_blocked=False, 
#         is_deleted=False
#     ).order_by('price')
    
#     # Get default variant (first available or cheapest)
#     default_variant = available_variants.first() if available_variants.exists() else None
    
#     # Calculate current stock
#     current_stock = default_variant.stock if default_variant else product.stock
    
#     # Check if product is in user's wishlist
#     in_wishlist = False
#     if request.user.is_authenticated:
#         in_wishlist = WishlistItem.objects.filter(
#             user=request.user, 
#             product=product
#         ).exists()
    
#     # Get related products
#     related_products = Product.objects.filter(
#         category=product.category,
#         is_blocked=False,
#         is_deleted=False
#     ).exclude(id=product.id)[:4]
    
#     context = {
#         'product': product,
#         'available_variants': available_variants,
#         'default_variant': default_variant,
#         'current_stock': current_stock,
#         'in_wishlist': in_wishlist,
#         'related_products': related_products,
#     }
    
#     return render(request, 'store/product_detail.html', context)

# Update the checkout view
# @login_required
# def checkout(request):
#     cart = get_object_or_404(Cart, user=request.user)
#     cart_items = cart.items.select_related('product', 'variant').prefetch_related('product__images')

#     # Filter out blocked/deleted products and categories
#     valid_items = []
#     for item in cart_items:
#         if (not item.product.is_blocked and not item.product.is_deleted and
#             not item.product.category.is_blocked and not item.product.category.is_deleted):
#             valid_items.append(item)

#     # If any invalid items were found, update the cart
#     if len(valid_items) != len(cart_items):
#         cart.items.exclude(pk__in=[item.pk for item in valid_items]).delete()
#         cart_items = valid_items

#     # Calculate order totals
#     subtotal = sum(item.subtotal() for item in cart_items)
#     tax = subtotal * Decimal('0.05')
#     shipping = Decimal('0.00') if subtotal > 1000 else Decimal('350.00')
#     discount = Decimal('0.00')
#     coupon_applied = False
#     coupon_code = ''
#     coupon_message = ''

#     # Handle coupon logic
#     if subtotal >= 1500:
#         coupon_code = 'AS100'
#         coupon_message = 'Flat ₹100 OFF'

#     # Handle POST actions
#     if request.method == 'POST':
#         # Handle address form submission
#         if 'submit_address_form' in request.POST:
#             address_id = request.POST.get('address_id')
#             if address_id:
#                 address = get_object_or_404(Address, id=address_id, user=request.user)
#                 form = AddressForm(request.POST, instance=address)
#             else:
#                 form = AddressForm(request.POST)

#             if form.is_valid():
#                 address = form.save(commit=False)
#                 address.user = request.user
#                 address.save()

#                 addresses = Address.objects.filter(user=request.user)
#                 html = render_to_string('store/includes/address_list.html', {
#                     'addresses': addresses
#                 }, request=request)

#                 return JsonResponse({
#                     'success': True,
#                     'html': html,
#                     'message': 'Address saved successfully!'
#                 })
#             else:
#                 # Return form with errors
#                 title = 'Edit Address' if address_id else 'Add New Address'
#                 html = render_to_string('store/includes/address_modal_form.html', {
#                     'form': form,
#                     'title': title
#                 }, request=request)
#                 return JsonResponse({'success': False, 'html': html})

#         # If user applies coupon
#         elif 'apply_coupon' in request.POST:
#             if coupon_code and request.POST.get('coupon_code', '').strip() == coupon_code:
#                 discount = Decimal('100.00')
#                 coupon_applied = True

#             if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
#                 return JsonResponse({
#                     'success': True,
#                     'discount': str(discount),
#                     'total': str(subtotal + tax + shipping - discount),
#                     'coupon_applied': True,
#                     'message': 'Coupon applied successfully!'
#                 })
#             else:
#                 messages.success(request, 'Coupon applied successfully!')
#                 return redirect('checkout')

#         # If user places order
#         elif 'place_order' in request.POST:
#             if not cart_items:
#                 messages.error(request, 'Your cart is empty')
#                 return redirect('checkout')

#             if coupon_code and request.POST.get('coupon_code', '').strip() == coupon_code:
#                 discount = Decimal('100.00')
#                 coupon_applied = True

#             address_id = request.POST.get('selected_address')
#             payment_method = request.POST.get('payment', 'COD')
            
#             if not address_id:
#                 messages.error(request, 'Please select a shipping address')
#                 return redirect('checkout')
                
#             address = get_object_or_404(Address, id=address_id, user=request.user)

#             # Check product availability before creating order
#             for item in cart_items:
#                 available_stock = item.variant.stock if item.variant else item.product.stock
#                 if item.quantity > available_stock:
#                     messages.error(request, f'Sorry, {item.product.name} only has {available_stock} items available')
#                     return redirect('checkout')

#             # Create the order
#             order = Order.objects.create(
#                 user=request.user,
#                 address=address,
#                 total_amount=subtotal + tax + shipping - discount,
#                 payment_method=payment_method
#             )

#             # Create order items
#             for item in cart_items:
#                 OrderItem.objects.create(
#                     order=order,
#                     product=item.product,
#                     quantity=item.quantity,
#                     price=item.get_price()
#                 )
                
#                 # Decrement stock
#                 if item.variant:
#                     item.variant.stock -= item.quantity
#                     item.variant.save()
                
#                 item.product.stock -= item.quantity
#                 item.product.save()

#             # Clear the cart
#             cart.items.all().delete()

#             if payment_method == 'COD':
#                 if shipping == 0:
#                     messages.success(request, "You've qualified for free shipping!")
#                 return redirect('order_success', order_id=order.id)
#             else:
#                 # Handle Razorpay payment
#                 try:
#                     razorpay_order = create_razorpay_order(
#                         amount=float(order.total_amount),
#                         receipt_id=order.id
#                     )
                    
#                     # Save Razorpay order ID to your order
#                     order.razorpay_order_id = razorpay_order['id']
#                     order.save()
                    
#                     context = {
#                         'order': order,
#                         'razorpay_order_id': razorpay_order['id'],
#                         'razorpay_amount': razorpay_order['amount'],
#                         'razorpay_currency': razorpay_order['currency'],
#                         'razorpay_key': settings.RAZORPAY_API_KEY,
#                         'callback_url': request.build_absolute_uri(reverse('payment_handler')),
#                         'user': {
#                             'name': request.user.get_full_name() or request.user.email.split('@')[0],
#                             'email': request.user.email,
#                             'contact': address.phone_number or '9999999999'  # Default number if not provided
#                         }
#                     }
#                     return render(request, 'store/payment.html', context)
                
#                 except Exception as e:
#                     # If Razorpay order creation fails, mark order as failed
#                     order.status = 'Failed'
#                     order.save()
#                     messages.error(request, f'Payment processing error: {str(e)}')
#                     return redirect('checkout')

#     total = subtotal + tax + shipping - discount

#     # Handle AJAX request for address form
#     if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
#         if 'get_address_form' in request.GET:
#             address_id = request.GET.get('address_id')
#             if address_id:
#                 address = get_object_or_404(Address, id=address_id, user=request.user)
#                 form = AddressForm(instance=address)
#                 title = 'Edit Address'
#             else:
#                 form = AddressForm()
#                 title = 'Add New Address'

#             html = render_to_string('store/includes/address_modal_form.html', {
#                 'form': form,
#                 'title': title
#             }, request=request)
#             return JsonResponse({'html': html})

#     return render(request, 'store/checkout.html', {
#         'addresses': Address.objects.filter(user=request.user),
#         'cart_items': cart_items,
#         'subtotal': subtotal,
#         'tax': tax,
#         'shipping': shipping,
#         'discount': discount,
#         'total': total,
#         'coupon_code': coupon_code,
#         'coupon_message': coupon_message,
#         'coupon_applied': coupon_applied,
#         'free_shipping': shipping == 0
#     })






def order_failed(request, message):
    return render(request, 'store/order_failed.html', {'message': message})

@login_required
def order_success(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    return render(request, 'store/order_success.html', {'order': order})

@login_required
def order_list(request):
    """Display user's orders with search functionality"""
    orders = Order.objects.filter(user=request.user).order_by('-created_at')
    
    # Search functionality
    search_query = request.GET.get('search', '').strip()
    if search_query:
        orders = orders.filter(
            Q(order_id__icontains=search_query) | 
            Q(status__icontains=search_query)
        )
    
    context = {
        'orders': orders,
        'search_query': search_query,
    }
    return render(request, 'store/orders.html', context)

@login_required
def order_detail(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    order_items = OrderItem.objects.filter(order=order).select_related('product')
    shipping_address = order.address

    context = {
        'order': order,
        'order_items': order_items,
        'shipping_address': shipping_address,
    }
    return render(request, 'store/order_detail.html', context)

@login_required
def download_invoice(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    
    # Verify the order belongs to the logged-in user
    if order.user != request.user:
        return HttpResponseForbidden("You don't have permission to view this invoice.")
    
    data = {
        'order': order,
        # Add any additional context data here
    }
    
    pdf = render_to_pdf('store/invoice.html', data)
    
    if pdf:
        response = HttpResponse(pdf, content_type='application/pdf')
        filename = f"Invoice_{order.order_id}.pdf"
        content = f"inline; filename={filename}"
        response['Content-Disposition'] = content
        return response
    return HttpResponse("Error generating PDF", status=400)


import logging

logger = logging.getLogger(__name__)

@login_required
@require_http_methods(["POST"])
def cancel_order(request, order_id):
    try:
        order = get_object_or_404(Order, order_id=order_id, user=request.user)
        if order.status in ['Delivered', 'Cancelled', 'Returned']:
            return JsonResponse({'success': False, 'message': 'This order cannot be cancelled.'})

        data = json.loads(request.body)
        cancellation_reason = data.get('reason', 'No reason provided')

        with transaction.atomic():
            order.status = 'Cancelled'
            order.remarks = cancellation_reason
            order.save()

            # Process refund if applicable (not COD)
            if order.is_paid and order.payment_method != 'COD':
                wallet, _ = Wallet.objects.get_or_create(user=request.user)
                refund_amount = order.total_amount
                WalletTransaction.objects.create(
                    wallet=wallet,
                    order=order,
                    transaction_type='credit',
                    amount=refund_amount,
                    description=f"Refund for cancelled order {order.order_id}"
                )
                wallet.balance += refund_amount
                wallet.save()
                order.refund_processed = True
                order.save()

            # Update all items to cancelled and restock
            for item in order.items.all():
                item.status = 'Cancelled'
                item.remarks = cancellation_reason
                item.save()
                item.product.stock += item.quantity
                item.product.save()

            return JsonResponse({
                'success': True,
                'message': 'Order cancelled successfully.',
                'new_status': 'Cancelled'
            })
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'An error occurred: {str(e)}'}, status=500)

@login_required
@require_http_methods(["POST"])
def return_order(request, order_id):
    order = get_object_or_404(Order, order_id=order_id, user=request.user)
    if order.status != 'Delivered':
        return JsonResponse({'success': False, 'message': 'Only delivered orders can be returned.'})

    data = json.loads(request.body)
    return_reason = data.get('reason', '')
    if not return_reason:
        return JsonResponse({'success': False, 'message': 'Return reason is required.'})

    order.status = 'Return Requested'
    order.remarks = return_reason
    order.save()
    
    return JsonResponse({
        'success': True,
        'message': 'Return request submitted. Waiting for approval.',
        'new_status': 'Return Requested'
    })

@require_POST
@login_required
def cancel_order_item(request, order_id, item_id):
    try:
        data = json.loads(request.body)
        reason = data.get('reason', '').strip()
        if not reason:
            return JsonResponse({'success': False, 'message': 'Reason is required.'})

        order = get_object_or_404(Order, order_id=order_id, user=request.user)
        item = get_object_or_404(OrderItem, id=item_id, order=order)

        if item.status in ['Delivered', 'Cancelled', 'Returned', 'Return Requested']:
            return JsonResponse({'success': False, 'message': 'Item cannot be cancelled.'})

        with transaction.atomic():
            item.status = 'Cancelled'
            item.remarks = reason
            item.save()

            # Update order status
            all_items = order.items.all()
            if all(item.status == 'Cancelled' for item in all_items):
                order.status = 'Cancelled'
            order.save()

            # Handle refund
            refund_amount = Decimal('0.00')
            if order.payment_method != 'COD' and not order.refund_processed:
                if order.items.count() == 1:
                    refund_amount = order.total  # Full refund for single-item orders
                else:
                    refund_amount = item.subtotal()  # Refund item subtotal only

                if refund_amount > 0:
                    wallet, _ = Wallet.objects.get_or_create(user=order.user)
                    WalletTransaction.objects.create(
                        wallet=wallet,
                        order=order,
                        transaction_type='credit',
                        amount=refund_amount,
                        description=f"Refund for cancelled item in order {order.order_id}"
                    )
                    wallet.balance += refund_amount
                    wallet.save()
                    if order.items.count() == 1:
                        order.refund_processed = True
                    order.save()

            # Restore stock
            product = item.product
            product.stock += item.quantity
            product.save()

        return JsonResponse({
            'success': True,
            'message': 'Item cancelled successfully.',
            'new_status': item.status
        })
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid request format.'})
    except Exception as e:
        logger.error(f"Error cancelling item {item_id} in order {order_id}: {str(e)}")
        return JsonResponse({'success': False, 'message': str(e)})

@require_POST
@login_required
def return_order_item(request, order_id, item_id):
    try:
        data = json.loads(request.body)
        reason = data.get('reason', '').strip()
        if not reason:
            return JsonResponse({'success': False, 'message': 'Reason is required.'})

        order = get_object_or_404(Order, order_id=order_id, user=request.user)
        item = get_object_or_404(OrderItem, id=item_id, order=order)

        if item.status != 'Delivered':
            return JsonResponse({'success': False, 'message': 'Item must be delivered to request a return.'})

        with transaction.atomic():
            item.status = 'Return Requested'
            item.remarks = reason
            item.save()

            # Update order status only if all items are return requested or returned
            all_items = order.items.all()
            if all(item.status in ['Return Requested', 'Returned'] for item in all_items):
                order.status = 'Return Requested'
            order.save()

            return JsonResponse({
                'success': True,
                'message': 'Return requested successfully.',
                'new_status': item.status
            })
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'message': 'Invalid request format.'})
    except Exception as e:
        logger.error(f"Error requesting return for item {item_id} in order {order_id}: {str(e)}")
        return JsonResponse({'success': False, 'message': str(e)})

def restock_items(order):
    """Helper function to restock inventory when order is cancelled/returned"""
    order_items = OrderItem.objects.filter(order=order).select_related('product', 'variant')

    for item in order_items:
        if item.variant:
            item.variant.stock += item.quantity
            item.variant.save()
        
        item.product.stock += item.quantity
        item.product.save()


########################################################################
# Add these views to your views.py file for email verification

import json
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
import datetime

@login_required
def check_email_availability(request):
    """Check if email is available for update"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            new_email = data.get('email', '').strip().lower()
            
            # Validate email format
            try:
                validate_email(new_email)
            except ValidationError:
                return JsonResponse({
                    'success': False, 
                    'message': 'Please enter a valid email address.'
                })
            
            # Check if email is the same as current email
            if new_email == request.user.email.lower():
                return JsonResponse({
                    'success': False, 
                    'message': 'This is your current email address.'
                })
            
            # Check if email already exists
            if User.objects.filter(email__iexact=new_email).exists():
                return JsonResponse({
                    'success': False, 
                    'message': 'User already exists with this email address.'
                })
            
            # Email is available, send OTP
            otp_code = str(random.randint(100000, 999999))
            
            # Store the new email and OTP in session for verification
            request.session['pending_email'] = new_email
            request.session['email_otp'] = otp_code
            request.session['email_otp_time'] = datetime.datetime.now().isoformat()
            
            # Send OTP to new email
            send_email_update_otp(new_email, otp_code)
            
            return JsonResponse({
                'success': True, 
                'message': 'OTP sent to your new email address. Please check your inbox.'
            })
            
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False, 
                'message': 'Invalid request format.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False, 
                'message': 'An error occurred. Please try again.'
            })
    
    return JsonResponse({'success': False, 'message': 'Invalid request method.'})

@login_required
def verify_email_otp(request):
    """Verify OTP and update email"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            entered_otp = data.get('otp', '').strip()
            
            # Get session data
            pending_email = request.session.get('pending_email')
            stored_otp = request.session.get('email_otp')
            otp_time_str = request.session.get('email_otp_time')
            
            if not all([pending_email, stored_otp, otp_time_str]):
                return JsonResponse({
                    'success': False, 
                    'message': 'OTP session expired. Please try again.'
                })
            
            # Check if OTP is expired (5 minutes)
            otp_time = datetime.datetime.fromisoformat(otp_time_str)
            if (datetime.datetime.now() - otp_time).seconds > 300:
                # Clear session data
                request.session.pop('pending_email', None)
                request.session.pop('email_otp', None)
                request.session.pop('email_otp_time', None)
                return JsonResponse({
                    'success': False, 
                    'message': 'OTP has expired. Please try again.'
                })
            
            # Verify OTP
            if stored_otp == entered_otp:
                # Double-check email availability before updating
                if User.objects.filter(email__iexact=pending_email).exists():
                    # Clear session data
                    request.session.pop('pending_email', None)
                    request.session.pop('email_otp', None)
                    request.session.pop('email_otp_time', None)
                    return JsonResponse({
                        'success': False, 
                        'message': 'Email is no longer available.'
                    })
                
                # Update user email
                request.user.email = pending_email
                request.user.save()
                
                # Clear session data
                request.session.pop('pending_email', None)
                request.session.pop('email_otp', None)
                request.session.pop('email_otp_time', None)
                
                return JsonResponse({
                    'success': True, 
                    'message': 'Email updated successfully!'
                })
            else:
                return JsonResponse({
                    'success': False, 
                    'message': 'Invalid OTP. Please try again.'
                })
                
        except json.JSONDecodeError:
            return JsonResponse({
                'success': False, 
                'message': 'Invalid request format.'
            })
        except Exception as e:
            return JsonResponse({
                'success': False, 
                'message': 'An error occurred. Please try again.'
            })
    
    return JsonResponse({'success': False, 'message': 'Invalid request method.'})

@login_required
def resend_email_otp(request):
    """Resend OTP to new email"""
    if request.method == 'POST':
        try:
            pending_email = request.session.get('pending_email')
            
            if not pending_email:
                return JsonResponse({
                    'success': False, 
                    'message': 'No email update in progress.'
                })
            
            # Generate new OTP
            otp_code = str(random.randint(100000, 999999))
            
            # Update session
            request.session['email_otp'] = otp_code
            request.session['email_otp_time'] = datetime.datetime.now().isoformat()
            
            # Send OTP
            send_email_update_otp(pending_email, otp_code)
            
            return JsonResponse({
                'success': True, 
                'message': 'New OTP sent to your email address.'
            })
            
        except Exception as e:
            return JsonResponse({
                'success': False, 
                'message': 'An error occurred. Please try again.'
            })
    
    return JsonResponse({'success': False, 'message': 'Invalid request method.'})

def send_email_update_otp(email, otp_code):
    """Send OTP email for email update"""
    subject = "Email Update Verification - Your OTP Code"
    message = f"""
    Hello,
    
    You have requested to update your email address. Your OTP code is: {otp_code}
    
    This code is valid for 5 minutes only.
    
    If you did not request this change, please ignore this email.
    
    Best regards,
    Aura Scents Team
    """
    send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [email])

############################################################################
import logging
@login_required
def checkout(request):
    cart = get_object_or_404(Cart, user=request.user)
    cart_items = cart.items.select_related('product', 'variant').prefetch_related('product__images')

    # Filter out blocked/deleted products and categories
    valid_items = []
    for item in cart_items:
        if (not item.product.is_blocked and not item.product.is_deleted and
            not item.product.category.is_blocked and not item.product.category.is_deleted):
            valid_items.append(item)

    # If any invalid items were found, update the cart
    if len(valid_items) != len(cart_items):
        cart.items.exclude(pk__in=[item.pk for item in valid_items]).delete()
        cart_items = valid_items

    # Calculate order totals
    subtotal = sum(item.subtotal() for item in cart_items)
    tax = subtotal * Decimal('0.05')
    shipping = Decimal('0.00') if subtotal > 1000 else Decimal('350.00')
    discount = Decimal('0.00')
    coupon_applied = False
    coupon_code = ''
    coupon_message = ''

    # Handle coupon logic
    if subtotal >= 1500:
        coupon_code = 'AS100'
        coupon_message = 'Flat ₹100 OFF'

    # Handle POST actions
    if request.method == 'POST':
        # Handle address form submission
        if 'submit_address_form' in request.POST:
            address_id = request.POST.get('address_id')
            if address_id:
                address = get_object_or_404(Address, id=address_id, user=request.user)
                form = AddressForm(request.POST, instance=address)
            else:
                form = AddressForm(request.POST)

            if form.is_valid():
                address = form.save(commit=False)
                address.user = request.user
                address.save()

                addresses = Address.objects.filter(user=request.user)
                html = render_to_string('store/includes/address_list.html', {
                    'addresses': addresses
                }, request=request)

                return JsonResponse({
                    'success': True,
                    'html': html,
                    'message': 'Address saved successfully!'
                })
            else:
                # Return form with errors
                title = 'Edit Address' if address_id else 'Add New Address'
                html = render_to_string('store/includes/address_modal_form.html', {
                    'form': form,
                    'title': title
                }, request=request)
                return JsonResponse({'success': False, 'html': html})

        # If user applies coupon
        elif 'apply_coupon' in request.POST:
            if coupon_code and request.POST.get('coupon_code', '').strip() == coupon_code:
                discount = Decimal('100.00')
                coupon_applied = True

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'discount': str(discount),
                    'total': str(subtotal + tax + shipping - discount),
                    'coupon_applied': True,
                    'message': 'Coupon applied successfully!'
                })
            else:
                messages.success(request, 'Coupon applied successfully!')
                return redirect('checkout')

        # If user places order
        elif 'place_order' in request.POST:
            logger = logging.getLogger(__name__)
            logger.debug(f"Place Order POST data: {request.POST}")
            logger.debug(f"Cart items: {len(cart_items)}")
            logger.debug(f"Selected address: {request.POST.get('selected_address')}")

            if not cart_items:
                logger.error("Cart is empty")
                error_response = {'error': 'Your cart is empty'}
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse(error_response, status=400)
                messages.error(request, error_response['error'])
                return redirect('checkout')

            if coupon_code and request.POST.get('coupon_code', '').strip() == coupon_code:
                discount = Decimal('100.00')
                coupon_applied = True

            address_id = request.POST.get('selected_address')
            if not address_id:
                logger.error("No address selected")
                error_response = {'error': 'Please select a shipping address'}
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse(error_response, status=400)
                messages.error(request, error_response['error'])
                return redirect('checkout')

            address = get_object_or_404(Address, id=address_id, user=request.user)
            payment_method = request.POST.get('payment', 'COD')

            # Check product availability before creating order
            for item in cart_items:
                available_stock = item.variant.stock if item.variant else item.product.stock
                if item.quantity > available_stock:
                    logger.error(f"Insufficient stock for {item.product.name}: requested {item.quantity}, available {available_stock}")
                    error_response = {'error': f'Sorry, {item.product.name} only has {available_stock} items available'}
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse(error_response, status=400)
                    messages.error(request, error_response['error'])
                    return redirect('checkout')

            # Create the order
            order = Order.objects.create(
                user=request.user,
                address=address,
                total_amount=subtotal + tax + shipping - discount,
                payment_method=payment_method
            )

            # Create order items
            for item in cart_items:
                OrderItem.objects.create(
                    order=order,
                    product=item.product,
                    variant=item.variant,
                    quantity=item.quantity,
                    price=item.get_price()
                )

                # Decrement stock
                if item.variant:
                    item.variant.stock -= item.quantity
                    item.variant.save()
                item.product.stock -= item.quantity
                item.product.save()

            # Clear the cart
            cart.items.all().delete()

            if payment_method == 'COD':
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'redirect_url': reverse('order_success', args=[order.id])
                    })
                messages.success(request, 'Order placed successfully!')
                return redirect('order_success', order_id=order.id)
            else:
                # Handle Razorpay payment
                try:
                    razorpay_order = create_razorpay_order(
                        amount=float(order.total_amount),
                        receipt_id=order.id
                    )

                    # Save Razorpay order ID to your order
                    order.razorpay_order_id = razorpay_order['id']
                    order.save()

                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'razorpay': True,
                            'redirect_url': reverse('payment_handler_init', args=[order.id]),
                            'razorpay_options': {
                                'key': settings.RAZORPAY_API_KEY,
                                'amount': int(float(order.total_amount) * 100),
                                'currency': settings.RAZORPAY_CURRENCY,
                                'name': "Aura Scents",
                                'description': f"Order #{order.id}",
                                'order_id': razorpay_order['id'],
                                'handler': request.build_absolute_uri(reverse('payment_handler')),
                                'prefill': {
                                    'name': request.user.get_full_name() or request.user.email.split('@')[0],
                                    'email': request.user.email,
                                    'contact': order.address.mobile_number or '9999999999'
                                },
                                'theme': {
                                    'color': '#7c3aed'
                                }
                            }
                        })

                    return redirect('payment_handler_init', order_id=order.id)

                except Exception as e:
                    logger.error(f"Razorpay error: {str(e)}")
                    order.status = 'Failed'
                    order.save()
                    error_response = {'error': f'Payment processing error: {str(e)}'}
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse(error_response, status=400)
                    messages.error(request, error_response['error'])
                    return redirect('checkout')

    # Handle AJAX request for address form
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        if 'get_address_form' in request.GET:
            address_id = request.GET.get('address_id')
            if address_id:
                address = get_object_or_404(Address, id=address_id, user=request.user)
                form = AddressForm(instance=address)
                title = 'Edit Address'
            else:
                form = AddressForm()
                title = 'Add New Address'

            html = render_to_string('store/includes/address_modal_form.html', {
                'form': form,
                'title': title
            }, request=request)
            return JsonResponse({'html': html})

    total = subtotal + tax + shipping - discount

    return render(request, 'store/checkout.html', {
        'addresses': Address.objects.filter(user=request.user),
        'cart_items': cart_items,
        'subtotal': subtotal,
        'tax': tax,
        'shipping': shipping,
        'discount': discount,
        'total': total,
        'coupon_code': coupon_code,
        'coupon_message': coupon_message,
        'coupon_applied': coupon_applied,
        'free_shipping': shipping == 0
    })

@csrf_exempt
def payment_handler(request):
    if request.method == 'POST':
        try:
            payment_id = request.POST.get('razorpay_payment_id', '')
            razorpay_order_id = request.POST.get('razorpay_order_id', '')
            signature = request.POST.get('razorpay_signature', '')

            if not all([payment_id, razorpay_order_id, signature]):
                return redirect('order_failed', message='Missing payment parameters')

            params_dict = {
                'razorpay_payment_id': payment_id,
                'razorpay_order_id': razorpay_order_id,
                'razorpay_signature': signature
            }

            # Verify the payment signature
            client.utility.verify_payment_signature(params_dict)

            # Payment was successful
            order = Order.objects.get(razorpay_order_id=razorpay_order_id)
            order.is_paid = True
            order.status = 'Processing'  # Changed from 'Paid' to 'Processing'
            order.save()

            return redirect('order_success', order_id=order.id)

        except Order.DoesNotExist:
            return redirect('order_failed', message='Invalid Order ID')
        except SignatureVerificationError:
            return redirect('order_failed', message='Invalid Payment Signature')
        except Exception as e:
            logger.error(f"Payment handler error: {str(e)}")
            return redirect('order_failed', message=str(e))

    return redirect('checkout')

def payment_handler_init(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)

    try:
        context = {
            'order': order,
            'razorpay_order_id': order.razorpay_order_id,
            'razorpay_amount': int(float(order.total_amount) * 100), # Convert to paise
            'razorpay_currency': settings.RAZORPAY_CURRENCY,
            'razorpay_key': settings.RAZORPAY_API_KEY,
            'callback_url': request.build_absolute_uri(reverse('payment_handler')),
            'user': {
                'name': request.user.get_full_name() or request.user.email.split('@')[0],
                'email': request.user.email,
                'contact': order.address.mobile_number or '9999999999'
            }
        }
        return render(request, 'store/payment.html', context)
    except Exception as e:
        messages.error(request, f'Payment initialization error: {str(e)}')
        return redirect('checkout')

@login_required
def wallet_view(request):
    wallet, created = Wallet.objects.get_or_create(user=request.user)
    transactions = wallet.transactions.all()
    return render(request, 'store/wallet.html', {
        'wallet': wallet,
        'transactions': transactions
    })