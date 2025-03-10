import json
import random
import string
from django.db.models import Prefetch
from django.db.models import F, Q
import stripe
from .forms import DISTRICT_THANA_MAPPING
from . import models
from .forms import JobApplicationForm, TrackingForm
from .models import Vacancy
from django.utils.timezone import now
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import ObjectDoesNotExist
from django.shortcuts import redirect
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.views.generic import ListView, DetailView, View
from datetime import datetime
from .forms import CheckoutForm, CouponForm, RefundForm, PaymentForm
from .models import Item, OrderItem, Order, Address, Payment, Coupon, Refund, UserProfile, Slider, Category, Subcategory,Color
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth.models import User
from django.db.models import  Sum
from django.http import HttpResponse
from django.template.loader import render_to_string
from xhtml2pdf import pisa
from .models import Order,ItemVariant
from decimal import Decimal
from .steadfast_service import SteadfastCourierService
import logging
import requests
logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY


def create_ref_code():
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=20))


def products(request):
    context = {
        'items': Item.objects.all()
    }
    return render(request, "products.html", context)


def is_valid_form(values):
    valid = True
    for field in values:
        if field == '':
            valid = False
    return valid




class CheckoutView(View):
    def get(self, *args, **kwargs):
        order = self.get_order()

        if not order.order_items.exists():
            messages.info(self.request, "Your cart is empty")
            return redirect("core:order-summary")

        # Calculate delivery charge based on address
        delivery_charge = self.calculate_delivery_charge(order)
        total_price = order.get_total()
        final_price = total_price + delivery_charge

        # Initialize form with user data if available
        form = CheckoutForm(request=self.request)
        if self.request.user.is_authenticated:
            form.fields['email'].initial = self.request.user.email

        context = {
            'form': form,
            'couponform': CouponForm(),
            'order': order,
            'delivery_charge': delivery_charge,
            'final_price': final_price,
            'total_price': total_price,
            'district_thana_mapping': json.dumps(DISTRICT_THANA_MAPPING),
        }

        self.add_default_addresses_to_context(context)
        return render(self.request, "checkout.html", context)
    def post(self, *args, **kwargs):
        order = self.get_order()
        form = CheckoutForm(self.request.POST, request=self.request)

        if not order.order_items.exists():
            messages.warning(self.request, "Your cart is empty")
            return redirect("core:order-summary")

        if form.is_valid():
            # Handle guest information
            if not order.user:
                order.email = form.cleaned_data.get('email')
                order.phone = form.cleaned_data.get('phone')
                order.guest_checkout = True

            # Update order details
            order.shipping_name = form.cleaned_data.get('shipping_name')
            order.phone_number = form.cleaned_data.get('phone_number')
            order.save()

            # Process addresses
            try:
                self.handle_addresses(form, order)
            except ObjectDoesNotExist:
                return redirect('core:checkout')

            # Final stock check
            if not self.check_stock_availability(order):
                return redirect("core:order-summary")

            # Process payment
            return self.process_payment(form, order)

        messages.warning(self.request, "Please correct the errors below")
        return render(self.request, 'checkout.html', {'form': form, 'order': order})

    def process_payment(self, form, order):
        payment_option = form.cleaned_data.get('payment_option')
        transaction_id = form.cleaned_data.get(f'{payment_option.lower()}_transaction_id')

        # Deduct stock and finalize order
        self.deduct_stock(order)
        order.ordered = True
        order.payment_method = payment_option
        order.transaction_id = transaction_id
        order.delivery_charge = self.calculate_delivery_charge(order)
        order.save()

        # Create courier consignment
        self.create_courier_consignment(order)

        # Clear session cart
        if 'cart' in self.request.session:
            del self.request.session['cart']
        self.request.session['cart_item_count'] = 0
        self.request.session.modified = True

        messages.success(self.request, "Order placed successfully!")
        return redirect('core:order-summary')

    def create_courier_consignment(self, order):
        courier_service = SteadfastCourierService()
        cod_amount = order.get_total() if order.payment_method == 'C' else 0.0

        order_data = {
            "invoice": f"ORD-{order.id}",
            "recipient_name": order.shipping_name,
            "recipient_phone": order.phone_number,
            "recipient_address": str(order.shipping_address),
            "cod_amount": float(cod_amount),
            "note": "Handle with care"
        }

        response = courier_service.create_order(order_data)
        if response.get('consignment'):
            order.consignment_id = response['consignment']['consignment_id']
            order.tracking_code = response['consignment']['tracking_code']
            order.delivery_status = response['consignment']['status']
            order.save()
            messages.info(self.request, f"Tracking code: {order.tracking_code}")
        else:
            messages.warning(self.request, "Courier service notification failed - contact support")

    def check_stock_availability(self, order):
        """Check if all items in the order are in stock."""
        for order_item in order.order_items.all():
            variant = get_object_or_404(ItemVariant, item=order_item.item, color=order_item.color)
            if variant.quantity_in_stock < order_item.quantity:
                return False
        return True

    def deduct_stock(self, order):
        """Deduct stock for each item in the order."""
        for order_item in order.order_items.all():
            variant = get_object_or_404(ItemVariant, item=order_item.item, color=order_item.color)
            variant.quantity_in_stock -= order_item.quantity
            variant.save()

    def calculate_delivery_charge(self, order):
        """Calculate delivery charge based on shipping address"""
        if order.shipping_address:
            if order.shipping_address.district.lower() == 'dhaka':
                return Decimal('70.00')
        return Decimal('110.00')

    def handle_addresses(self, form, order):
        """Process shipping/billing addresses"""
        # Shipping address
        if form.cleaned_data.get('use_default_shipping'):
            if self.request.user.is_authenticated:
                order.shipping_address = Address.objects.filter(
                    user=self.request.user,
                    address_type='S',
                    default=True
                ).first()
            if not order.shipping_address:
                messages.error(self.request, "No default shipping address available")
                raise ObjectDoesNotExist
        else:
            order.shipping_address = self.create_address(
                form,
                'shipping',
                user=self.request.user if self.request.user.is_authenticated else None
            )

        if form.cleaned_data.get('same_billing_address'):
            order.billing_address = order.shipping_address
        elif form.cleaned_data.get('use_default_billing'):
            if self.request.user.is_authenticated:
                order.billing_address = Address.objects.filter(
                    user=self.request.user,
                    address_type='B',
                    default=True
                ).first()
            if not order.billing_address:
                messages.error(self.request, "No default billing address available")
                raise ObjectDoesNotExist
        else:
            order.billing_address = self.create_address(
                form,
                'billing',
                user=self.request.user if self.request.user.is_authenticated else None
            )

        order.save()

    def create_address(self, form, address_type, user=None):
        address = Address(
            user=user or None ,
            street_address=form.cleaned_data.get(f'{address_type}_address'),
            apartment_address=form.cleaned_data.get(f'{address_type}_address2'),
            zip=form.cleaned_data.get(f'{address_type}_zip'),
            country=form.cleaned_data.get(f'{address_type}_country'),
            district=form.cleaned_data.get('district'),
            thana=form.cleaned_data.get(f'{address_type}_thana'),
            address_type=address_type
        )
        address.save()
        return address

    def add_default_addresses_to_context(self, context):
        if self.request.user.is_authenticated:
            shipping_address_qs = Address.objects.filter(user=self.request.user, address_type='S', default=True)
            billing_address_qs = Address.objects.filter(user=self.request.user, address_type='B', default=True)

            if shipping_address_qs.exists():
                context.update({'default_shipping_address': shipping_address_qs.first()})
            if billing_address_qs.exists():
                context.update({'default_billing_address': billing_address_qs.first()})

    def should_include_billing_address(self, form):
        return form.cleaned_data.get('same_billing_address') is not True

    def get_order(self):
        return Order.objects.filter(
            Q(user=self.request.user if self.request.user.is_authenticated else None) |
            Q(session_key=self.request.session.session_key),
            ordered=False
        ).first()

class PaymentView(View):
    def get(self, *args, **kwargs):
        order = Order.objects.get(user=self.request.user, ordered=False)
        if order.billing_address:
            context = {
                'order': order,
                'DISPLAY_COUPON_FORM': False,
                'STRIPE_PUBLIC_KEY' : settings.STRIPE_PUBLIC_KEY
            }
            userprofile = self.request.user.userprofile
            if userprofile.one_click_purchasing:
                # fetch the users card list
                cards = stripe.Customer.list_sources(
                    userprofile.stripe_customer_id,
                    limit=3,
                    object='card'
                )
                card_list = cards['data']
                if len(card_list) > 0:
                    # update the context with the default card
                    context.update({
                        'card': card_list[0]
                    })
            return render(self.request, "payment.html", context)
        else:
            messages.warning(
                self.request, "You have not added a billing address")
            return redirect("core:checkout")

    def post(self, *args, **kwargs):
        order = Order.objects.get(user=self.request.user, ordered=False)
        form = PaymentForm(self.request.POST)
        userprofile = UserProfile.objects.get(user=self.request.user)
        if form.is_valid():
            token = form.cleaned_data.get('stripeToken')
            save = form.cleaned_data.get('save')
            use_default = form.cleaned_data.get('use_default')

            if save:
                if userprofile.stripe_customer_id != '' and userprofile.stripe_customer_id is not None:
                    customer = stripe.Customer.retrieve(
                        userprofile.stripe_customer_id)
                    customer.sources.create(source=token)

                else:
                    customer = stripe.Customer.create(
                        email=self.request.user.email,
                    )
                    customer.sources.create(source=token)
                    userprofile.stripe_customer_id = customer['id']
                    userprofile.one_click_purchasing = True
                    userprofile.save()

            amount = int(order.get_total() * 100)

            try:

                if use_default or save:
                    # charge the customer because we cannot charge the token more than once
                    charge = stripe.Charge.create(
                        amount=amount,  # cents
                        currency="usd",
                        customer=userprofile.stripe_customer_id
                    )
                else:
                    # charge once off on the token
                    charge = stripe.Charge.create(
                        amount=amount,  # cents
                        currency="usd",
                        source=token
                    )

                # create the payment
                payment = Payment()
                payment.stripe_charge_id = charge['id']
                payment.user = self.request.user
                payment.amount = order.get_total()
                payment.save()

                # assign the payment to the order

                order_items = order.items.all()
                order_items.update(ordered=True)
                for item in order_items:
                    item.save()

                order.ordered = True
                order.payment = payment
                order.ref_code = create_ref_code()
                order.save()

                messages.success(self.request, "Your order was successful!")
                return redirect("/")

            except stripe.error.CardError as e:
                body = e.json_body
                err = body.get('error', {})
                messages.warning(self.request, f"{err.get('message')}")
                return redirect("/")

            except stripe.error.RateLimitError as e:
                # Too many requests made to the API too quickly
                messages.warning(self.request, "Rate limit error")
                return redirect("/")

            except stripe.error.InvalidRequestError as e:
                # Invalid parameters were supplied to Stripe's API
                print(e)
                messages.warning(self.request, "Invalid parameters")
                return redirect("/")

            except stripe.error.AuthenticationError as e:
                # Authentication with Stripe's API failed
                # (maybe you changed API keys recently)
                messages.warning(self.request, "Not authenticated")
                return redirect("/")

            except stripe.error.APIConnectionError as e:
                # Network communication with Stripe failed
                messages.warning(self.request, "Network error")
                return redirect("/")

            except stripe.error.StripeError as e:
                # Display a very generic error to the user, and maybe send
                # yourself an email
                messages.warning(
                    self.request, "Something went wrong. You were not charged. Please try again.")
                return redirect("/")

            except Exception as e:
                # send an email to ourselves
                messages.warning(
                    self.request, "A serious error occurred. We have been notifed.")
                return redirect("/")

        messages.warning(self.request, "Invalid data received")
        return redirect("/payment/stripe/")


class HomeView(ListView):
    model = Item
    paginate_by = 10
    template_name = "home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Create session if it doesn't exist
        if not self.request.session.session_key:
            self.request.session.create()

        # Get the appropriate order based on authentication status
        if self.request.user.is_authenticated:
            order = Order.objects.filter(user=self.request.user, ordered=False).first()
        else:
            order = Order.objects.filter(
                session_key=self.request.session.session_key,
                ordered=False
            ).first()

        # Homepage content
        context.update({
            'sliders': Slider.objects.all(),
            'categories': Category.objects.prefetch_related(
                Prefetch('subcategories', queryset=Subcategory.objects.all())
            ),
            'discounted_items': Item.objects.filter(
                discount_price__isnull=False,
                discount_price__lt=F('price')
            )[:4],
            'cart_items_count': order.order_items.count() if order else 0
        })

        return context

class OrderSummaryView(View):
    def get(self, *args, **kwargs):
        order = self.get_order()  # Retrieve order via unified method

        if not order or not order.order_items.exists():
            messages.warning(self.request, "Your cart is empty")
            return redirect("core:home")

        context = self.build_context(order)
        return render(self.request, 'order_summary.html', context)


    def get_order(self):
        """Retrieve order for both authenticated and guest users"""
        if self.request.user.is_authenticated:
            return Order.objects.filter(
                user=self.request.user,
                ordered=False
            ).prefetch_related('order_items').first()
        else:
            if not self.request.session.session_key:
                return None
            return Order.objects.filter(
                session_key=self.request.session.session_key,
                ordered=False
            ).prefetch_related('order_items').first()

    def build_context(self, order):
        return {
            'object': order,
            'order_items': order.order_items.all(),
            'order_total': order.get_total(),
            'delivery_charge': order.delivery_charge or Decimal('110.00'),
            'original_prices': [
                item.original_price
                for item in order.order_items.all()
                if item.original_price
            ],}

    def handle_authenticated_user(self):
        try:
            order = Order.objects.get(user=self.request.user, ordered=False)
            if not order.order_items.exists():
                messages.warning(self.request, "You do not have any items in your active order.")
                return redirect("core:home")  # Use named URL pattern

            context = {
                'object': order,
                'order_items': order.order_items.all(),
                'order_total': order.get_total(),
                'original_prices': [item.original_price for item in order.order_items.all() if item.original_price],
            }
            return render(self.request, 'order_summary.html', context)
        except Order.DoesNotExist:
            messages.warning(self.request, "You do not have an active order.")
            return redirect("core:home")  # Use named URL pattern

    def handle_unauthenticated_user(self):
        # Retrieve the order using the session key
        order = Order.objects.filter(
            session_key=self.request.session.session_key,
            ordered=False
        ).first()

        if order and order.order_items.exists():
            context = {
                'object': order,
                'order_items': order.order_items.all(),
                'order_total': order.get_total(),
                'original_prices': [item.original_price for item in order.order_items.all() if item.original_price],
                'delivery_charge': order.delivery_charge if order.delivery_charge else Decimal('110.00'),
            }
            return render(self.request, 'order_summary.html', context)
        else:
            messages.warning(self.request, "Your cart is empty.")
            return redirect("core:home")

class ItemDetailView(DetailView):
    model = Item
    template_name = "product.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        item = self.object
        available_variants = item.variants.all()

        # Get available colors as Color instances
        available_colors = available_variants.values_list('color', flat=True).distinct()
        context['available_colors'] = Color.objects.filter(id__in=available_colors)

        # Get related products
        related_products = Item.objects.filter(category=item.category).exclude(id=item.id)[:4]

        # Check for low stock items
        low_stock_items = []
        for variant in available_variants:
            if variant.quantity_in_stock < 5:  # Define your low stock threshold
                low_stock_items.append(variant)

        # Add data to context
        context['related_products'] = related_products
        context['description_points'] = item.description.split(',') if item.description else []
        context['low_stock_items'] = low_stock_items  # Pass low stock items to the template

        return context


def add_to_cart(request, slug):
    item = get_object_or_404(Item, slug=slug)
    color_id = request.POST.get('color')

    if not color_id:
        messages.warning(request, "Please select a color.")
        return redirect("core:product", slug=slug)

    color = get_object_or_404(Color, id=color_id)
    variant = get_object_or_404(ItemVariant, item=item, color=color)

    # Ensure session exists
    if not request.session.session_key:
        request.session.create()

    # Get or create order for both authenticated and guest users
    order, created = Order.objects.get_or_create(
        session_key=request.session.session_key,
        user=request.user if request.user.is_authenticated else None,
        ordered=False,
        defaults={'ordered_date': timezone.now()}
    )

    # Check existing items in the order
    existing_item = order.order_items.filter(item=item, color=color).first()

    if existing_item:
        if variant.quantity_in_stock > existing_item.quantity:
            existing_item.quantity += 1
            existing_item.save()
            messages.info(request, "Quantity updated.")
        else:
            messages.warning(request, "Not enough stock available.")
    else:
        if variant.quantity_in_stock > 0:
            OrderItem.objects.create(
                item=item,
                order=order,
                color=color,
                quantity=1,
                item_price=item.discount_price or item.price,
                original_price=item.price
            )
            messages.info(request, "Item added to cart")
        else:
            messages.warning(request, "This item is out of stock.")

    # Update cart count (convert Decimal to int for session)
    cart_count = order.order_items.aggregate(
        total=Sum('quantity')
    )['total'] or 0
    request.session['cart_item_count'] = int(cart_count)
    request.session.modified = True

    return redirect("core:order-summary")


def remove_from_cart(request, slug):
    item = get_object_or_404(Item, slug=slug)

    # Get the appropriate order
    if request.user.is_authenticated:
        order = Order.objects.filter(user=request.user, ordered=False).first()
    else:
        order = Order.objects.filter(
            session_key=request.session.session_key,
            ordered=False
        ).first()

    if not order:
        messages.warning(request, "No active order found.")
        return redirect("core:order-summary")

    order_item = order.order_items.filter(item=item).first()

    if order_item:
        order_item.delete()
        messages.info(request, "Item removed from cart.")

        # Update cart count
        cart_count = order.order_items.aggregate(
            total=Sum('quantity')
        )['total'] or 0
        request.session['cart_item_count'] = int(cart_count)
        request.session.modified = True
    else:
        messages.info(request, "Item not found in cart.")

    return redirect("core:order-summary")


def remove_single_item_from_cart(request, slug):
    item = get_object_or_404(Item, slug=slug)

    # Get the appropriate order
    if request.user.is_authenticated:
        order = Order.objects.filter(user=request.user, ordered=False).first()
    else:
        order = Order.objects.filter(
            session_key=request.session.session_key,
            ordered=False
        ).first()

    if not order:
        messages.warning(request, "No active order found.")
        return redirect("core:order-summary")

    order_item = order.order_items.filter(item=item).first()

    if order_item:
        if order_item.quantity > 1:
            order_item.quantity -= 1
            order_item.save()
            messages.info(request, "Quantity updated.")
        else:
            order_item.delete()
            messages.info(request, "Item removed from cart.")

        # Update cart count
        cart_count = order.order_items.aggregate(
            total=Sum('quantity')
        )['total'] or 0
        request.session['cart_item_count'] = int(cart_count)
        request.session.modified = True
    else:
        messages.info(request, "Item not found in cart.")

    return redirect("core:order-summary")


def get_coupon(request, code):
    try:
        coupon = Coupon.objects.get(code=code)
        if coupon.is_valid():
            return coupon
        else:
            messages.info(request, "This coupon is not valid or has expired.")
            return None
    except Coupon.DoesNotExist:
        messages.info(request, "This coupon does not exist.")
        return None


class AddCouponView(View):
    def post(self, *args, **kwargs):
        form = CouponForm(self.request.POST or None)
        if form.is_valid():
            code = form.cleaned_data.get('code')
            coupon = get_coupon(self.request, code)  # Get the coupon object

            if coupon and coupon.is_valid():  # Check if the coupon exists and is valid
                try:
                    order = Order.objects.get(user=self.request.user, ordered=False)
                    order.coupon = coupon  # Apply the coupon
                    order.save()
                    messages.success(self.request, f"Successfully added coupon '{coupon.code}'")
                except Order.DoesNotExist:
                    messages.info(self.request, "You do not have an active order")
            else:
                messages.warning(self.request, "This coupon is not valid or has expired.")
        else:
            messages.warning(self.request, "Invalid coupon form submission.")

        return redirect("core:checkout")

class RequestRefundView(View):
    def get(self, *args, **kwargs):
        form = RefundForm()
        context = {
            'form': form
        }
        return render(self.request, "request_refund.html", context)

    def post(self, *args, **kwargs):
        form = RefundForm(self.request.POST)
        if form.is_valid():
            ref_code = form.cleaned_data.get('ref_code')
            message = form.cleaned_data.get('message')
            email = form.cleaned_data.get('email')
            # edit the order
            try:
                order = Order.objects.get(ref_code=ref_code)
                order.refund_requested = True
                order.save()

                # store the refund
                refund = Refund()
                refund.order = order
                refund.reason = message
                refund.email = email
                refund.save()

                messages.info(self.request, "Your request was received.")
                return redirect("core:request-refund")

            except ObjectDoesNotExist:
                messages.info(self.request, "This order does not exist.")
                return redirect("core:request-refund")


def product_list(request, slug=None, subcategory_slug=None):
    sliders = Slider.objects.all()

    # Fetch all categories for the navbar
    categories = Category.objects.prefetch_related('subcategories').all()

    # If a category slug is provided, fetch that category
    if slug:
        category = get_object_or_404(Category, slug=slug)

        # If a subcategory slug is provided, fetch the subcategory and filter items
        if subcategory_slug:
            subcategory = get_object_or_404(Subcategory, slug=subcategory_slug)
            items = Item.objects.filter(subcategory=subcategory)
        else:
            # If no subcategory, fetch all items in this category
            items = Item.objects.filter(category=category)

    else:
        # If no category slug is provided, fetch all items (you can modify this part if needed)
        category = None
        items = Item.objects.all()

    return render(request, 'category_detail.html', {
        'sliders': sliders,
        'category': category,  # The current category
        'categories': categories,  # List of all categories for the navbar
        'items': items,  # List of items (filtered by category or subcategory)
    })
#search view
class SearchResultsView(ListView):
    model = Item
    template_name = 'search_results.html'
    context_object_name = 'items'

    def get_queryset(self):
        query = self.request.GET.get('q')
        if query:
            return Item.objects.filter(title__icontains=query)
        return Item.objects.all()

def about_us(request):
    return render(request, 'about_us.html')

def return_policy(request):
    return render (request, 'return.html')
def contact (request):
    return render(request, 'contact.html')

def career_view(request):
    if request.method == 'POST':
        form = JobApplicationForm(request.POST, request.FILES)
        if form.is_valid():
            form.save()
            # Re-initialize the form to show an empty form after saving the data
            form = JobApplicationForm()
            return render(request, 'career.html', {'form': form, 'success': True})
    else:
        form = JobApplicationForm()

    return render(request, 'career.html', {'form': form})


def vacancy_list(request):
    vacancies = Vacancy.objects.filter(is_active=True).order_by('-posted_date')
    return render(request, 'vacancies.html', {'vacancies': vacancies})


def print_invoice(request, order_id):
    order = Order.objects.get(id=order_id)

    # Render the invoice template with the order details
    html = render_to_string('invoice_template.html', {'order': order})

    # Create a PDF response
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="invoice_{order.id}.pdf"'

    # Create a PDF from the rendered HTML
    pisa_status = pisa.CreatePDF(html, dest=response)

    if pisa_status.err:
        return HttpResponse('We had some errors <pre>' + html + '</pre>')

    return response

def track_parcel(request):
    tracking_info = None
    form = TrackingForm()

    if request.method == 'POST':
        form = TrackingForm(request.POST)
        if form.is_valid():
            tracking_code = form.cleaned_data['tracking_code']
            tracking_info = get_tracking_info(tracking_code)

    return render(request, 'track_parcel.html', {'form': form, 'tracking_info': tracking_info})

def get_tracking_info(tracking_code):
    api_url = f"https://steadfast.com.bd/t/{tracking_code}"

    try:
        response = requests.get(api_url)
        response.raise_for_status()  # Raise an error for bad responses (4xx or 5xx)
        return response.json()  # Assuming the API returns JSON data
    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
    except requests.exceptions.RequestException as req_err:
        print(f"Request error occurred: {req_err}")
    except ValueError as json_err:
        print(f"JSON decode error: {json_err}")

    return None  # Return None if there was an error