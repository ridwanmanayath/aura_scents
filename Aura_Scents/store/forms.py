from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from back_office.models import User

from .models import Address

import os

class RegistrationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']
  

class LoginForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)


User = get_user_model()

class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'profile_image']

        widgets = {
            'profile_image': forms.FileInput(),  # Use plain FileInput instead of ClearableFileInput
        }
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make profile_image optional
        self.fields['profile_image'].required = False

        # Make email read-only (not required, not editable)
        self.fields['email'].disabled = True
        
        # Add custom attributes to the profile_image field
        self.fields['profile_image'].widget.attrs.update({
            'accept': 'image/jpeg,image/jpg,image/png',
            'class': 'hidden',
            'id': 'id_profile_image'
        })
    
    def clean_profile_image(self):
        profile_image = self.cleaned_data.get('profile_image')
        
        if profile_image:
            # Check file size (limit to 5MB)
            if profile_image.size > 5 * 1024 * 1024:
                raise forms.ValidationError('Image file too large. Please keep it under 5MB.')
            
            # Check file extension
            valid_extensions = ['.jpg', '.jpeg', '.png']
            ext = os.path.splitext(profile_image.name)[1].lower()
            if ext not in valid_extensions:
                raise forms.ValidationError('Please upload a valid image file (JPEG, JPG, or PNG).')
                
        return profile_image

class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = [
            'first_name', 'last_name', 'address', 'city', 'state',
            'pincode', 'mobile_number', 'alternate_mobile_number'
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent',
                'required': True
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent',
                'required': True
            }),
            'address': forms.Textarea(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent resize-none',
                'rows': 3,
                'required': True
            }),
            'city': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent',
                'required': True
            }),
            'state': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent',
                'required': True
            }),
            'pincode': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent',
                'maxlength': '6',
                'required': True
            }),
            'mobile_number': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent',
                'maxlength': '10',
                'type': 'tel',
                'required': True
            }),
            'alternate_mobile_number': forms.TextInput(attrs={
                'class': 'w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent',
                'maxlength': '10',
                'type': 'tel'
            }),
        }

    def clean_pincode(self):
        pincode = self.cleaned_data.get('pincode')
        if pincode and not pincode.isdigit():
            raise forms.ValidationError('PIN code must contain only digits.')
        if pincode and len(pincode) != 6:
            raise forms.ValidationError('PIN code must be exactly 6 digits.')
        return pincode

    def clean_mobile_number(self):
        mobile = self.cleaned_data.get('mobile_number')
        if mobile and not mobile.isdigit():
            raise forms.ValidationError('Mobile number must contain only digits.')
        if mobile and len(mobile) != 10:
            raise forms.ValidationError('Mobile number must be exactly 10 digits.')
        return mobile

    def clean_alternate_mobile_number(self):
        alt_mobile = self.cleaned_data.get('alternate_mobile_number')
        if alt_mobile and not alt_mobile.isdigit():
            raise forms.ValidationError('Alternate mobile number must contain only digits.')
        if alt_mobile and len(alt_mobile) != 10:
            raise forms.ValidationError('Alternate mobile number must be exactly 10 digits.')
        return alt_mobile
