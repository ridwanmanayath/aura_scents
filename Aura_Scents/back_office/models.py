from django.contrib.auth.models import AbstractUser
from django.db import models

from django.utils import timezone
from PIL import Image
import os
from uuid import uuid4

from django.core.exceptions import ValidationError
from decimal import Decimal
import re


def user_profile_image_path(instance, filename):
    """Generate upload path for user profile images"""
    ext = filename.split('.')[-1]
    filename = f'user_{instance.id}_profile.{ext}'
    return os.path.join('profile_images', filename)

class User(AbstractUser):
    is_blocked = models.BooleanField(default=False)
    email = models.EmailField(unique=True)
    profile_image = models.ImageField(
        upload_to=user_profile_image_path, 
        blank=True, 
        null=True,
        help_text="Upload a profile image (JPG, JPEG, PNG only)"
    )

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return self.email
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        
        # Resize profile image if it exists
        if self.profile_image:
            img_path = self.profile_image.path
            if os.path.exists(img_path):
                with Image.open(img_path) as img:
                    # Convert to RGB if necessary (for PNG with transparency)
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")
                    
                    # Resize to 400x400 pixels
                    max_size = (400, 400)
                    img.thumbnail(max_size, Image.Resampling.LANCZOS)
                    img.save(img_path, quality=85, optimize=True)

class Category(models.Model):
    name = models.CharField(max_length=255,unique=True)
    is_deleted = models.BooleanField(default=False)
    is_blocked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
    

# Creating a custom path to avoid name conflicts
def product_image_upload_path(instance, filename):
    ext = filename.split('.')[-1]
    filename = f"{uuid4().hex}.{ext}"
    return os.path.join('products', filename)


#Product Model
class Product(models.Model):
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products')
    name = models.CharField(max_length=255)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.PositiveIntegerField()
    is_blocked = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.name

# Units choices
UNIT_CHOICES = [
    ('ml', 'Milliliter'),
    ('g', 'Gram'),
    ('oz', 'Ounce'),
]

class ProductVariant(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    volume = models.DecimalField(max_digits=6, decimal_places=2)
    unit = models.CharField(max_length=5, choices=UNIT_CHOICES)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.PositiveIntegerField()
    is_deleted = models.BooleanField(default=False)
    is_blocked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('product', 'volume', 'unit')

    def __str__(self):
        return f"{self.product.name} - {self.volume} {self.unit}"


# Product Image Model
class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to=product_image_upload_path)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        img = Image.open(self.image.path)
        img = img.convert("RGB")
        img = img.resize((600, 600), Image.LANCZOS)
        img.save(self.image.path)


# Coupon Model
class Coupon(models.Model):
    COUPON_TYPES = [
        ('percentage', 'Percentage Discount'),
        ('fixed', 'Fixed Amount Discount'),
    ]

    code = models.CharField(max_length=20, unique=True, help_text="Unique coupon code (e.g., SAVE10)")
    description = models.TextField(blank=True, help_text="Description of the coupon")
    coupon_type = models.CharField(max_length=20, choices=COUPON_TYPES, default='percentage')
    discount_value = models.DecimalField(max_digits=10, decimal_places=2, help_text="Discount amount or percentage")
    minimum_order_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Minimum order amount to apply coupon")
    max_discount_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Maximum discount cap for percentage coupons")
    valid_from = models.DateTimeField(default=timezone.now, help_text="Coupon validity start date")
    valid_until = models.DateTimeField(help_text="Coupon validity end date")
    usage_limit = models.PositiveIntegerField(null=True, blank=True, help_text="Maximum number of times coupon can be used")
    usage_count = models.PositiveIntegerField(default=0, help_text="Number of times coupon has been used")
    is_active = models.BooleanField(default=True, help_text="Whether the coupon is active")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.code

    def clean(self):
        """Custom validation for the Coupon model"""
        # Ensure code is uppercase and alphanumeric
        if not re.match(r'^[A-Z0-9]+$', self.code):
            raise ValidationError("Coupon code must be uppercase alphanumeric characters only.")

        # Validate discount value based on coupon type
        if self.coupon_type == 'percentage':
            if not (0 <= self.discount_value <= 100):
                raise ValidationError("Percentage discount must be between 0 and 100.")
        elif self.coupon_type == 'fixed':
            if self.discount_value <= 0:
                raise ValidationError("Fixed discount amount must be greater than 0.")

        # Ensure max_discount_amount is set for percentage coupons if provided
        if self.coupon_type == 'percentage' and self.max_discount_amount is not None:
            if self.max_discount_amount <= 0:
                raise ValidationError("Maximum discount amount must be greater than 0.")

        # Ensure valid_until is after valid_from
        if self.valid_until <= self.valid_from:
            raise ValidationError("Valid until date must be after valid from date.")

        # Ensure minimum_order_amount is non-negative
        if self.minimum_order_amount < 0:
            raise ValidationError("Minimum order amount cannot be negative.")

    def save(self, *args, **kwargs):
        """Override save to run full_clean for validations"""
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def is_valid(self):
        """Check if the coupon is valid for use"""
        now = timezone.now()
        return (
            self.is_active and
            self.valid_from <= now <= self.valid_until and
            (self.usage_limit is None or self.usage_count < self.usage_limit)
        )

    def apply_discount(self, order_total):
        """Calculate discount amount based on coupon type"""
        if not self.is_valid:
            return Decimal('0.00')

        if self.coupon_type == 'percentage':
            discount = (self.discount_value / Decimal('100')) * order_total
            if self.max_discount_amount and discount > self.max_discount_amount:
                discount = self.max_discount_amount
        else:  # fixed
            discount = self.discount_value

        return min(discount, order_total)  # Ensure discount doesn't exceed order total


