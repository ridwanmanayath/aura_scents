from django.contrib.auth.models import AbstractUser
from django.db import models

from django.utils import timezone
from PIL import Image
import os
from uuid import uuid4

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

