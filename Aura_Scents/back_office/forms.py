
from django import forms
from django.contrib.auth.forms import AuthenticationForm

from django import forms
from .models import Product, ProductImage,Coupon
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import InMemoryUploadedFile



class UserLoginForm(AuthenticationForm):
    username = forms.EmailField(label='Email')


# Coupon Form
class CouponForm(forms.ModelForm):
    class Meta:
        model = Coupon
        fields = [
            'code', 'description', 'coupon_type', 'discount_value',
            'minimum_order_amount', 'max_discount_amount', 'valid_from',
            'valid_until', 'usage_limit', 'is_active'
        ]
        widgets = {
            'valid_from': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'valid_until': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'description': forms.Textarea(attrs={'rows': 4}),
        }

    def clean(self):
        cleaned_data = super().clean()
        coupon_type = cleaned_data.get('coupon_type')
        discount_value = cleaned_data.get('discount_value')
        max_discount_amount = cleaned_data.get('max_discount_amount')

        # Additional form-level validation
        if coupon_type == 'percentage' and discount_value > 100:
            self.add_error('discount_value', "Percentage discount cannot exceed 100%.")
        if coupon_type == 'fixed' and discount_value <= 0:
            self.add_error('discount_value', "Fixed discount must be greater than 0.")
        if max_discount_amount is not None and max_discount_amount <= 0:
            self.add_error('max_discount_amount', "Maximum discount amount must be positive.")

        return cleaned_data

