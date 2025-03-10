import requests
from django.conf import settings
from requests.exceptions import RequestException


class SteadfastCourierService:
    BASE_URL = "https://portal.packzy.com/api/v1"

    def __init__(self):
        self.headers = {
            "Api-Key": settings.STEADFAST_API_KEY,
            "Secret-Key": settings.STEADFAST_SECRET_KEY,
            "Content-Type": "application/json"
        }

    def create_order(self, order_data):
        """Create single order"""
        url = f"{self.BASE_URL}/create_order"
        try:
            response = requests.post(url, json=order_data, headers=self.headers)
            return response.json()
        except RequestException as e:
            return {"error": str(e)}

    def bulk_create_orders(self, orders):
        """Create bulk orders (max 500 per request)"""
        url = f"{self.BASE_URL}/create_order/bulk-order"
        payload = {"data": orders}
        try:
            response = requests.post(url, json=payload, headers=self.headers)
            return response.json()
        except RequestException as e:
            return {"error": str(e)}

    def get_delivery_status(self, identifier, identifier_type):
        """Check delivery status by different identifiers"""
        endpoints = {
            'consignment_id': f"/status_by_cid/{identifier}",
            'invoice': f"/status_by_invoice/{identifier}",
            'tracking_code': f"/status_by_trackingcode/{identifier}"
        }
        url = f"{self.BASE_URL}{endpoints[identifier_type]}"
        try:
            response = requests.get(url, headers=self.headers)
            return response.json()
        except RequestException as e:
            return {"error": str(e)}

    def get_current_balance(self):
        """Check current account balance"""
        url = f"{self.BASE_URL}/get_balance"
        try:
            response = requests.get(url, headers=self.headers)
            return response.json()
        except RequestException as e:
            return {"error": str(e)}
