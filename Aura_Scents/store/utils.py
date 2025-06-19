from io import BytesIO
from django.http import HttpResponse
from django.template.loader import get_template
from xhtml2pdf import pisa

import razorpay
from django.conf import settings


def render_to_pdf(template_src, context_dict={}):
    template = get_template(template_src)
    html = template.render(context_dict)
    result = BytesIO()
    
    # Better encoding handling
    pdf = pisa.pisaDocument(
        BytesIO(html.encode("UTF-8")), 
        result,
        encoding='UTF-8'
    )
    
    if not pdf.err:
        return HttpResponse(result.getvalue(), content_type='application/pdf')
    return None



client = razorpay.Client(auth=(settings.RAZORPAY_API_KEY, settings.RAZORPAY_API_SECRET))

def create_razorpay_order(amount, receipt_id, currency=settings.RAZORPAY_CURRENCY):
    data = {
        'amount': int(amount * 100),  # Razorpay expects amount in paise
        'currency': currency,
        'receipt': str(receipt_id),
        'payment_capture': 1  # Auto-capture payment
    }
    order = client.order.create(data=data)
    return order