# core/middleware.py
from django.utils.deprecation import MiddlewareMixin
from django.db import transaction
from .models import Order, ItemVariant


class CartValidationMiddleware(MiddlewareMixin):
    """Ensures valid cart session and maintains cart integrity"""

    def process_request(self, request):
        # Ensure session exists
        if not request.session.session_key:
            request.session.create()

        # Initialize cart count in session
        if 'cart_item_count' not in request.session:
            request.session['cart_item_count'] = 0

        # For authenticated users, migrate session cart to database
        if request.user.is_authenticated:
            self.migrate_guest_cart(request)

        # Validate and update cart contents
        self.validate_cart_contents(request)

        return None

    def migrate_guest_cart(self, request):
        """Transfer guest cart to user account on login"""
        session_key = request.session.session_key
        if session_key:
            with transaction.atomic():
                guest_order = Order.objects.filter(
                    session_key=session_key,
                    ordered=False
                ).first()

                if guest_order:
                    user_order, created = Order.objects.get_or_create(
                        user=request.user,
                        ordered=False,
                        defaults={'session_key': session_key}
                    )

                    if not created:
                        # Merge guest cart items into user's existing cart
                        for item in guest_order.order_items.all():
                            existing = user_order.order_items.filter(
                                item=item.item,
                                color=item.color
                            ).first()

                            if existing:
                                existing.quantity += item.quantity
                                existing.save()
                            else:
                                item.order = user_order
                                item.save()

                        guest_order.delete()

                    # Update session cart count
                    request.session['cart_item_count'] = user_order.order_items.count()
                    request.session.modified = True

    def validate_cart_contents(self, request):
        """Validate cart items against current stock and prices"""
        order = Order.objects.get_for_user(request)

        if order and not order.ordered:
            modified = False
            for item in order.order_items.all():
                try:
                    variant = ItemVariant.objects.get(
                        item=item.item,
                        color=item.color
                    )

                    # Check stock availability
                    if variant.quantity_in_stock < item.quantity:
                        item.quantity = variant.quantity_in_stock
                        item.save()
                        modified = True
                        if variant.quantity_in_stock == 0:
                            item.delete()
                            modified = True

                    # Check price consistency
                    current_price = item.item.discount_price or item.item.price
                    if item.item_price != current_price:
                        item.item_price = current_price
                        item.amount_saved = (item.original_price - current_price) * item.quantity
                        item.save()
                        modified = True

                except ItemVariant.DoesNotExist:
                    item.delete()
                    modified = True

            if modified:
                # Update session cart count
                request.session['cart_item_count'] = order.order_items.count()
                request.session.modified = True