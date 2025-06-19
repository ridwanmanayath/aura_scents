
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect
from .forms import UserLoginForm

from django.contrib.admin.views.decorators import staff_member_required

from django.contrib import messages

from .models import User, Category

from django.core.paginator import Paginator
from django.db.models import Q

from django.views.decorators.http import require_POST

from django.shortcuts import render, redirect, get_object_or_404
from .models import Product, ProductImage, Category,ProductVariant

from uuid import uuid4
import os
from django.core.exceptions import ValidationError

from store.models import Order

from django.db import transaction



#Admin View
def admin_login(request):
    if request.method == 'POST':
        form = UserLoginForm(data=request.POST)
        if form.is_valid():
            login(request, form.get_user())
            return redirect('admin_dashboard')
    else:
        form = UserLoginForm()
    return render(request, 'back_office/admin_login.html', {'form': form})

# Dashboard View
@staff_member_required(login_url='admin_login') 
def admin_dashboard(request):
    return render(request, 'back_office/admin_dashboard.html')


# Log Out View
def admin_logout(request):
    logout(request)
    messages.success(request, "You have been logged out successfully.")
    return redirect('admin_login')


# User List and Search  
@staff_member_required(login_url='admin_login') 
def user_list(request):
    query = request.GET.get('q')
    users = User.objects.filter(is_superuser=False)

    if query:
        users = users.filter(Q(username__icontains=query) | Q(email__icontains=query))

    users = users.order_by('-id')  # Latest first
    paginator = Paginator(users, 5)
    page = request.GET.get('page')
    users = paginator.get_page(page)

    return render(request, 'back_office/user_list.html', {'users': users, 'query': query})

# Block/Unblock Users
@require_POST
def toggle_block_user(request, user_id):
    user = User.objects.get(id=user_id)
    user.is_blocked = not user.is_blocked
    user.save()
    messages.success(request, f"User {'blocked' if user.is_blocked else 'unblocked'} successfully.")
    return redirect('user_list')


# Category List
@staff_member_required(login_url='admin_login') 
def category_list(request):
    query = request.GET.get('q')
    categories = Category.objects.filter(is_deleted=False)

    if query:
        categories = categories.filter(name__icontains=query)

    categories = categories.order_by('-created_at')
    paginator = Paginator(categories, 5)
    page = request.GET.get('page')
    categories = paginator.get_page(page)

    return render(request, 'back_office/category_list.html', {'categories': categories, 'query': query})

# Category Add
@staff_member_required(login_url='admin_login') 
def category_add(request):
    if request.method == 'POST':
        name = request.POST['name']
        is_blocked = not ('category-status' in request.POST)
        Category.objects.create(name=(name), is_blocked=is_blocked)
        return redirect('category_list')
    return render(request, 'back_office/category_add.html')

#Category Edit
@staff_member_required(login_url='admin_login') 
def category_edit(request, category_id):
    category = Category.objects.get(id=category_id)
    if request.method == 'POST':
        category.name = request.POST['name']
        category.is_blocked = not ('category-status' in request.POST)       
        category.save()
        return redirect('category_list')
    return render(request, 'back_office/category_edit.html', {'category': category})

#Category Delete
@staff_member_required(login_url='admin_login') 
def category_delete(request, category_id):
    category = Category.objects.get(id=category_id)
    category.is_deleted = True
    category.save()
    return redirect('category_list')

#Product List
@staff_member_required(login_url='admin_login') 
def product_list(request):
    query = request.GET.get('q', '')
    products = Product.objects.filter(is_deleted=False)

    if query:
        products = products.filter(name__icontains=query)

    paginator = Paginator(products, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return render(request, 'back_office/product_list.html', {'page_obj': page_obj, 'query':query} )





#Product Manage
@staff_member_required(login_url='admin_login')
def product_manage(request, product_id=None):
    # Determine if this is an add or edit operation
    is_edit = product_id is not None
    
    if is_edit:
        product = get_object_or_404(Product, id=product_id)
        variants = ProductVariant.objects.filter(product=product)
        images = ProductImage.objects.filter(product=product)
    else:
        product = None
        variants = []
        images = []

    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description')
        price = request.POST.get('price')
        stock = request.POST.get('stock')
        category_id = request.POST.get('category')
        is_blocked = not ('product-status' in request.POST)
        new_images = request.FILES.getlist('images')
        use_variants = request.POST.get('use_variants') == 'on'
        
        # Handle image removals in edit mode
        removed_images_str = request.POST.get('removed_images', '')
        removed_image_ids = []
        if removed_images_str:
            try:
                removed_image_ids = [int(id.strip()) for id in removed_images_str.split(',') if id.strip()]
            except ValueError:
                pass  # Invalid format, ignore

        # Validation
        if not name or not description or not category_id:
            error = "Name, description and category are required fields."
            categories = Category.objects.filter(is_deleted=False, is_blocked=False)
            return render(request, 'back_office/product_manage.html', locals())

        # Image validation - check total images after removals and additions
        if is_edit:
            # Count existing images that won't be removed
            existing_image_count = ProductImage.objects.filter(product=product).exclude(id__in=removed_image_ids).count()
            total_images = existing_image_count + len(new_images)
        else:
            total_images = len(new_images)

        if total_images < 3:
            error = f"At least 3 images are required. You currently have {total_images} image(s)."
            categories = Category.objects.filter(is_deleted=False, is_blocked=False)
            return render(request, 'back_office/product_manage.html', locals())

        if not use_variants:
            try:
                price = float(price)
                stock = int(stock)
                if price < 0 or stock < 0:
                    raise ValidationError("Price and stock must be non-negative.")
            except (ValueError, TypeError):
                error = "Invalid price or stock format."
                categories = Category.objects.filter(is_deleted=False, is_blocked=False)
                return render(request, 'back_office/product_manage.html', locals())
        else:
            price = 0  # Placeholder
            stock = 0  # Will sum from variants

        category = get_object_or_404(Category, id=category_id)

        # Create or Update Product
        if is_edit:
            product.name = name
            product.description = description
            product.price = price
            product.stock = stock
            product.is_blocked = is_blocked
            product.category = category
            product.save()
        else:
            product = Product.objects.create(
                name=name,
                description=description,
                price=price,
                stock=stock,
                is_blocked=is_blocked,
                category=category
            )

        # Handle Image Removals (for edit mode)
        if is_edit and removed_image_ids:
            try:
                # Get the images to be removed
                images_to_remove = ProductImage.objects.filter(
                    product=product, 
                    id__in=removed_image_ids
                )
                
                # Delete the actual image files from storage (optional)
                for img in images_to_remove:
                    if img.image and hasattr(img.image, 'delete'):
                        img.image.delete(save=False)
                
                # Delete the database records
                images_to_remove.delete()
                
            except Exception as e:
                # Log the error if you have logging set up
                print(f"Error removing images: {e}")

        # Handle New Image Additions
        if new_images:
            for image in new_images:
                try:
                    ProductImage.objects.create(product=product, image=image)
                except Exception as e:
                    # Log the error if you have logging set up
                    print(f"Error adding image: {e}")

        # Handle Variants
        if use_variants:
            variant_volumes = request.POST.getlist('variant_volume[]')
            variant_units = request.POST.getlist('variant_unit[]')
            variant_prices = request.POST.getlist('variant_price[]')
            variant_stocks = request.POST.getlist('variant_stock[]')
            variant_ids = request.POST.getlist('variant_id[]')

            # Validate variant data
            if not variant_volumes or not variant_units or not variant_prices or not variant_stocks:
                error = "All variant fields are required when using variants."
                categories = Category.objects.filter(is_deleted=False, is_blocked=False)
                return render(request, 'back_office/product_manage.html', locals())

            # First delete any variants that were removed
            if is_edit:
                existing_variant_ids = [str(v.id) for v in variants]
                variants_to_remove = [v_id for v_id in existing_variant_ids if v_id not in variant_ids]
                if variants_to_remove:
                    ProductVariant.objects.filter(id__in=variants_to_remove).delete()

            total_stock = 0
            valid_variants_count = 0
            
            for idx, (vol, unit, pr, stk) in enumerate(zip(variant_volumes, variant_units, variant_prices, variant_stocks)):
                if not vol or not unit or not pr or not stk:
                    continue  # Skip incomplete rows

                try:
                    vol = float(vol)
                    pr = float(pr)
                    stk = int(stk)
                    
                    if vol <= 0 or pr < 0 or stk < 0:
                        error = "Variant volume must be greater than 0, price and stock must be non-negative."
                        categories = Category.objects.filter(is_deleted=False, is_blocked=False)
                        return render(request, 'back_office/product_manage.html', locals())
                    
                    total_stock += stk
                    valid_variants_count += 1
                    
                except (ValueError, TypeError):
                    error = "Invalid variant data format."
                    categories = Category.objects.filter(is_deleted=False, is_blocked=False)
                    return render(request, 'back_office/product_manage.html', locals())

                variant_id = variant_ids[idx] if idx < len(variant_ids) and variant_ids[idx] else None
                
                if variant_id:  # Update existing variant
                    try:
                        variant = ProductVariant.objects.get(id=variant_id, product=product)
                        variant.volume = vol
                        variant.unit = unit
                        variant.price = pr
                        variant.stock = stk
                        variant.save()
                    except ProductVariant.DoesNotExist:
                        # Create new variant if the existing one doesn't exist
                        ProductVariant.objects.create(
                            product=product,
                            volume=vol,
                            unit=unit,
                            price=pr,
                            stock=stk
                        )
                else:  # Create new variant
                    ProductVariant.objects.create(
                        product=product,
                        volume=vol,
                        unit=unit,
                        price=pr,
                        stock=stk
                    )
            
            # Ensure at least one valid variant exists
            if valid_variants_count == 0:
                error = "At least one valid variant is required when using variants."
                categories = Category.objects.filter(is_deleted=False, is_blocked=False)
                return render(request, 'back_office/product_manage.html', locals())
            
            # Update product stock to sum of all variants
            product.stock = total_stock
            product.save()
        else:
            # If not using variants, delete any existing variants
            if is_edit:
                ProductVariant.objects.filter(product=product).delete()

        
        return redirect('product_list')

    categories = Category.objects.filter(is_deleted=False, is_blocked=False)
    return render(request, 'back_office/product_manage.html', {
        'categories': categories,
        'product': product,
        'variants': variants,
        'images': images,
        'is_edit': is_edit
    })



# Product Edit
@staff_member_required(login_url='admin_login') 
def product_edit(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    categories = Category.objects.filter(is_deleted=False)

    if request.method == 'POST':
        name = request.POST.get('name')
        description = request.POST.get('description')
        price = request.POST.get('price')
        stock = request.POST.get('stock')
        category_id = request.POST.get('category')
        is_blocked =  not ('product-status' in request.POST)
        images = request.FILES.getlist('images')

        if not name or not description or not price or not stock or not category_id:
            error = "All fields are required."
            return render(request, 'back_office/product_edit.html', {
                'error': error,
                'product': product,
                'edit': True,
                'form_data': request.POST,
                'categories': categories
            })

        product.name = name
        product.description = description
        product.price = price
        product.stock = stock
        product.category_id = category_id
        product.is_blocked = is_blocked
        product.save()

        for image in images:
            ProductImage.objects.create(product=product, image=image)

        return redirect('product_list')

    return render(request, 'back_office/product_edit.html', {
        'product': product,
        'edit': True,
        'categories': categories,
        'is_blocked': product.is_blocked,
    })


# Product Delete
@staff_member_required(login_url='admin_login') 
def product_delete(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    product.is_deleted = True
    product.save()
    return redirect('product_list')

def order_list(request):
    orders = Order.objects.select_related('user').all()
    
    # === SEARCH ===
    query = request.GET.get('q')
    if query:
        orders = orders.filter(
            Q(order_id__icontains=query) |
            Q(user__email__icontains=query) |
            Q(user__username__icontains=query)
        )

    # === FILTER BY STATUS ===
    status_filter = request.GET.get('status')
    if status_filter:
        orders = orders.filter(status=status_filter)

    # === SORTING ===
    sort_by = request.GET.get('sort')
    if sort_by == 'date_asc':
        orders = orders.order_by('created_at')
    else:  # default or date_desc
        orders = orders.order_by('-created_at')

    # === PAGINATION ===
    paginator = Paginator(orders, 10)  # 10 orders per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'orders': page_obj,
        'query': query,
        'status_filter': status_filter,
        'sort_by': sort_by,
    }
    return render(request, 'back_office/order_list.html', context)



def order_detail(request, order_id):
    order = get_object_or_404(
        Order.objects.prefetch_related('items__product__images', 'items__product__variants'),
        id=order_id
    )
    return render(request, 'back_office/order_detail.html', {'order': order})



def update_order_status(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    
    if request.method == 'POST':
        new_status = request.POST.get('status')
        old_status = order.status
        
        if new_status != old_status:
            order.status = new_status
            order.save()
            messages.success(request, f'Order status updated to {new_status}')
            
            # Handle inventory for cancellations/returns
            if new_status in ['Cancelled', 'Returned']:
                with transaction.atomic():
                    for item in order.items.all():
                        product = item.product
                        product.stock += item.quantity
                        product.save()
            
        return redirect('order_details', order_id=order.id)
    
    return redirect('order_list')




