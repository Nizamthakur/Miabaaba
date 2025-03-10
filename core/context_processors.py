# core/context_processors.py
from .models import Order


def cart_item_count(request):
    """Add cart item count to all templates"""
    count = 0
    try:
        if request.user.is_authenticated:
            # Authenticated user - get their order
            order = Order.objects.filter(
                user=request.user,
                ordered=False
            ).first()
        else:
            # Guest user - get session-based order
            if not request.session.session_key:
                request.session.create()

            order = Order.objects.filter(
                session_key=request.session.session_key,
                ordered=False
            ).first()

        if order:
            count = order.order_items.count()

    except Exception as e:
        # Handle potential database errors gracefully
        pass

    return {'cart_item_count': count}