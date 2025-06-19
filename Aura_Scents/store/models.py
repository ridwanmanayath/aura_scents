from django.db import models
from django.conf import settings
from back_office.models import User,Product,ProductVariant
import random
import datetime
from django.utils import timezone
from decimal import Decimal

class OTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    otp_code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    is_verified = models.BooleanField(default=False)

    def is_expired(self):
        return (datetime.datetime.now(datetime.timezone.utc) - self.created_at).seconds > 300  # OTP For 5 Minutes
    



class Address(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='addresses')
    
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    
    address = models.TextField()  
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    pincode = models.CharField(max_length=20)
    
    mobile_number = models.CharField(max_length=20)
    alternate_mobile_number = models.CharField(max_length=20, blank=True, null=True)
    
    def __str__(self):
        return f"{self.first_name} {self.last_name}, {self.address}, {self.city}"
    

class WishlistItem(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='wishlist_items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='wishlisted_by')
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'product')  # Prevents duplicates in wishlist

    def __str__(self):
        return f"{self.user.email} - {self.product.name}"



class Cart(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.email}'s cart"

class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, null=True, blank=True)
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        # Ensure unique cart items per product-variant combination
        unique_together = ('cart', 'product', 'variant')

    def __str__(self):
        if self.variant:
            return f"{self.product.name} - {self.variant.volume}{self.variant.unit} ({self.quantity})"
        return f"{self.product.name} ({self.quantity})"

    def subtotal(self):
        if self.variant:
            return self.quantity * self.variant.price
        return self.quantity * self.product.price
    
    def get_price(self):
        """Get the price of the item (variant price if available, otherwise product price)"""
        return self.variant.price if self.variant else self.product.price
    
    def get_stock(self):
        """Get available stock for this item"""
        return self.variant.stock if self.variant else self.product.stock
    
    def get_display_name(self):
        """Get display name including variant info"""
        base_name = self.product.name
        if self.variant:
            return f"{base_name} ({self.variant.volume}{self.variant.unit}) × {self.quantity}"
        return f"{base_name} × {self.quantity}"
    

class Order(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    address = models.ForeignKey(Address, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=50, default='COD')
    is_paid = models.BooleanField(default=False)
    status = models.CharField(max_length=50, default='Pending')
    order_id = models.CharField(max_length=20, unique=True, blank=True)

    def __str__(self):
        return f"Order {self.order_id} by {self.user.email}"

    def save(self, *args, **kwargs):
        if not self.order_id:
            date_part = timezone.now().strftime("%Y%m%d")
            random_part = str(random.randint(1000, 9999))
            self.order_id = f"ORD-{date_part}-{random_part}"
            while Order.objects.filter(order_id=self.order_id).exists():
                random_part = str(random.randint(1000, 9999))
                self.order_id = f"ORD-{date_part}-{random_part}"
        super().save(*args, **kwargs)

    @property
    def subtotal(self):
        """Calculate subtotal by summing all order items"""
        if hasattr(self, '_subtotal'):
            return self._subtotal
        self._subtotal = sum(
            Decimal(str(item.price)) * item.quantity 
            for item in self.items.all()
        )
        return self._subtotal

    @property
    def tax(self):
        """Calculate 5% tax on subtotal"""
        return self.subtotal * Decimal('0.05')

    @property
    def shipping_cost(self):
        """Calculate shipping cost (free if subtotal > 1000, else 350)"""
        return Decimal('0') if self.subtotal > Decimal('1000') else Decimal('350')

    @property
    def discount(self):
        """Calculate discount (100 if subtotal >= 1500)"""
        return Decimal('100') if self.subtotal >= Decimal('1500') else Decimal('0')

    @property
    def total(self):
        """Calculate total amount including all components"""
        return self.subtotal - self.discount + self.tax + self.shipping_cost

    class Meta:
        ordering = ['-created_at']

class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True)
    quantity = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    
    def subtotal(self):
        return self.price * self.quantity   



