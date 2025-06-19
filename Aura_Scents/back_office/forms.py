
from django import forms
from django.contrib.auth.forms import AuthenticationForm

from django import forms
from .models import Product, ProductImage
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import InMemoryUploadedFile



class UserLoginForm(AuthenticationForm):
    username = forms.EmailField(label='Email')

