
from .models import Cart

def cart_quantity(request):
    total_quantity = 0
    if request.user.is_authenticated:
        cart = Cart.objects.filter(user=request.user).first()
        if cart:
            total_quantity = sum(item.quantity for item in cart.items.all())
    return {'cart_quantity': total_quantity}