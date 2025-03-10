
from django import forms
import re
from .models import JobApplication
from django.core.exceptions import ValidationError
from .models import Item
# Define PAYMENT_CHOICES
from django import forms
from .models import Item  # Ensure you import your Item model
import re
from django.core.exceptions import ValidationError

# Payment choices
PAYMENT_CHOICES = [
    ('N', 'Nagad'),
    ('B', 'Bikash'),
    ('C', 'Cash on Delivery'),
]

# Full District and Thana mapping for Bangladesh
DISTRICT_THANA_MAPPING = {
    "Dhaka": [
        "Dhanmondi", "Mirpur", "Uttara", "Gulshan", "Mohammadpur", "Tejgaon", "Badda",
        "Savar", "Keraniganj", "Narayanganj Sadar", "Narayanganj", "Tongi", "Vashantek",
        "Shyampur", "Khilkhet", "Rampura", "Malibagh", "Mugda", "Shahjahanpur", "Kotwali",
        "Sutrapur", "Lalbagh", "Hazaribagh", "Kafrul", "Pallabi", "Bashundhara R/A",
        "Bashabo", "Khilgaon", "Shahbagh", "Motijheel", "Paltan", "Sadarghat", "Chawkbazar",
        "Wari", "Bangshal", "Kotwali", "Sutrapur", "Shyampur", "Dakkhinkhan", "Bashundhara R/A",
    ],
    "Chittagong": [
        "Chittagong Sadar", "Pahartali", "Double Mooring", "Patenga", "Bhaluka", "Anwara",
        "Banshkhali", "Boalkhali", "Fatikchhari", "Lohagara", "Mirsharai", "Patiya",
        "Rangunia", "Raozan", "Sandwip", "Satkania", "Sandwip", "Sadar", "Banshkhali",
        "Brahmanbaria", "Cox's Bazar",
    ],
    "Khulna": [
        "Khulna Sadar", "Dighalia", "Dumuria", "Khalishpur", "Sonadanga", "Batiaghata",
        "Paikgachha", "Rupsha", "Terokhada", "Fultala", "Koyra", "Dumuria", "Sadar",
        "Shyamnagar", "Satkhira",
    ],
    "Rajshahi": [
        "Rajshahi Sadar", "Bagmara", "Puthia", "Durgapur", "Tanore", "Mohonpur", "Charghat",
        "Godagari", "Nawabganj", "Shahjadpur", "Bholahat", "Sujanagar",
    ],
    "Barisal": [
        "Barisal Sadar", "Bakerganj", "Banaripara", "Gournadi", "Hizla", "Mehendiganj",
        "Muladi", "Wazirpur", "Agailjhara", "Jhalokati",
    ],
    "Sylhet": [
        "Sylhet Sadar", "Beanibazar", "Bishwanath", "Companiganj", "Dakshin Surma",
        "Gowainghat", "Jaintiapur", "Moulvibazar", "Rajnagar", "Sreemangal", "South Surma",
    ],
    "Narayanganj": [
        "Narayanganj Sadar", "Araihazar", "Bandar", "Bholabo", "Narayanganj", "Sonargaon",
        "Siddhirganj", "Kanchpur", "Kotarpar",
    ],
    "Mymensingh": [
        "Mymensingh Sadar", "Gaffargaon", "Haluaghat", "Mymensingh", "Nandail", "Phulpur",
        "Trishal", "Muktagachha",
    ],
    "Cumilla": [
        "Cumilla Sadar", "Barura", "Brahmanpara", "Burichang", "Daudkandi", "Debidwar",
        "Homna", "Laksam", "Muradnagar", "Nangalkot", "Titas",
    ],
    "Pabna": [
        "Pabna Sadar", "Atghoria", "Bera", "Bhangura", "Chatmohar", "Faridpur", "Ishwardi",
        "Santhia", "Sujanagar",
    ],
    "Jessore": [
        "Jessore Sadar", "Abhaynagar", "Bagherpara", "Chanchra", "Chaugachha", "Jhikargachha",
        "Keshabpur", "Manirampur", "Sharsha",
    ],
    "Netrakona": [
        "Netrakona Sadar", "Atpara", "Barhatta", "Durgapur", "Khaliajuri", "Kenduli",
        "Madan", "Mohanganj", "Purbadhala", "Shyampur",
    ],
    "Brahmanbaria": [
        "Brahmanbaria Sadar", "Ashuganj", "Bancharampur", "Brahmanbaria", "Kasba",
        "Nabinagar", "Nasirnagar", "Sarail", "Bijoynagar",
    ],
    "Noakhali": [
        "Noakhali Sadar", "Companiganj", "Hatiya", "Senbagh", "Sonaimuri", "Subarnachar",
        "Chatkhil", "Begumganj", "Lalpur",
    ],
    "Panchagarh": [
        "Panchagarh Sadar", "Boda", "Debiganj", "Tetulia", "Atwari",
    ],
    "Thakurgaon": [
        "Thakurgaon Sadar", "Pirganj", "Ranishankail", "Haripur", "Baliadangi",
    ],
    "Dinajpur": [
        "Dinajpur Sadar", "Birampur", "Chirirbandar", "Ghoraghat", "Kahalu", "Kaharol",
        "Nawabganj", "Parbatipur", "Sujanagar", "Hakimpur",
    ],
    "Kurigram": [
        "Kurigram Sadar", "Bhurungamari", "Chilmari", "Nageshwari", "Rajarhat", "Ranishankail",
        "Rowmari", "Ulipur",
    ],
    "Lalmonirhat": [
        "Lalmonirhat Sadar", "Aditmari", "Hatibandha", "Kaliganj", "Patgram",
    ],
    "Moulvibazar": [
        "Moulvibazar Sadar", "Barlekha", "Juri", "Kamalganj", "Kulaura", "Rajnagar",
        "Sreemangal", "Sadar",
    ],
    "Habiganj": [
        "Habiganj Sadar", "Ajmiriganj", "Baniachong", "Chunarughat", "Lakhai", "Madhabpur",
        "Nabiganj", "Shaistaganj",
    ],
    "Sunamganj": [
        "Sunamganj Sadar", "Bishwambharpur", "Chhatak", "Derai", "Dharamapasha", "Jamalganj",
        "Juri", "Shantiganj", "Sullah", "Tahirpur",
    ],
    "Sherpur": [
        "Sherpur Sadar", "Nokla", "Jamalpur", "Sreebardi", "Nalitabari", "Mohammadpur",
    ],
    "Jamalpur": [
        "Jamalpur Sadar", "Baksiganj", "Dewanganj", "Islampur", "Jamalpur", "Madhupur",
        "Sarishabari", "Sharisabari", "Saturia",
    ],
    "Netrokona": [
        "Netrokona Sadar", "Atpara", "Barhatta", "Durgapur", "Khaliajuri", "Kenduli",
        "Madan", "Mohanganj", "Purbadhala", "Shyampur",
    ],
    "Bagerhat": [
        "Bagerhat Sadar", "Chitalmari", "Mollahat", "Morrelganj", "Sadar", "Kachua",
        "Fakirhat", "Rampal", "Sharankhola",
    ],
    "Patuakhali": [
        "Patuakhali Sadar", "Bauphal", "Galachipa", "Kalapara", "Mir zaganj", "Sadar", "Dumki", "Tajumuddin",
    ],
    "Pirojpur": [
        "Pirojpur Sadar", "Bhandaria", "Kawkhali", "Mathbaria", "Nazirpur", "Nesarabad",
        "Swarupkathi",
    ],
    "Satkhira": [
        "Satkhira Sadar", "Assasuni", "Debhata", "Kalaroa", "Kaliganj", "Shyamnagar",
        "Tala", "Sadar",
    ],
    "Kishoreganj": [
        "Kishoreganj Sadar", "Austagram", "Bajitpur", "Bhairab", "Hossainpur", "Itna",
        "Katiadi", "Kishoreganj", "Nikli", "Pakundia", "Tarakandi",
    ],
    "Narsingdi": [
        "Narsingdi Sadar", "Belabo", "Monohordi", "Raipura", "Shibpur", "Narsingdi",
        "Palash", "Shibpur",
    ],
    "Manikganj": [
        "Manikganj Sadar", "Dhamrai", "Ghior", "Harirampur", "Saturia", "Shibalaya",
        "Singair", "Manikganj",
    ],
    "Chandpur": [
        "Chandpur Sadar", "Faridganj", "Haimchar", "Kachua", "Shahrasti", "Shahrasti",
        "Matlab Uttar", "Matlab Dakkhin",
    ],
    "Cox's Bazar": [
        "Cox's Bazar Sadar", "Chakaria", "Maheshkhali", "Kutubdia", "Ramu", "Teknaf",
        "Ukhiya", "Pekua",
    ],
    "Jhalokati": [
        "Jhalokati Sadar", "Kathalia", "Rajapur", "Jhalokati", "Bhandaria",
    ],
    "Jhenaidah": [
        "Jhenaidah Sadar", "Chirirbandar", "Shailkupa", "Kaliganj", "Kotchandpur",
        "Madhupur", "Sadar",
    ],
    "Lakshmipur": [
        "Lakshmipur Sadar", "Raipur", "Ramganj", "Ramgati", "Kamolnagar", "Lakshmipur",
    ],
    "Madaripur": [
        "Madaripur Sadar", "Shibchar", "Kalkini", "Madaripur", "Rajoir",
    ],
    "Magura": [
        "Magura Sadar", "Shalikha", "Sreepur", "Magura", "Mohammadpur",
    ],
    "Meherpur": [
        "Meherpur Sadar", "Gangni", "Mujibnagar", "Meherpur", "Sadar",
    ],
}

DISTRICT_CHOICES = [("", "Select District")] + [(district, district) for district in DISTRICT_THANA_MAPPING.keys()]

# Phone number validation function
def validate_phone_number(value):
    if not re.match(r'^\+?1?\d{9,15}$', value):  # Matches international formats
        raise ValidationError('Invalid phone number. Ensure it is entered correctly.')

class CheckoutForm(forms.Form):
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control'})
    )
    shipping_name = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={'placeholder': 'Full Name', 'class': 'form-control'})
    )
    phone_number = forms.CharField(
        max_length=15,
        required=True,
        validators=[validate_phone_number],
        widget=forms.TextInput(attrs={'placeholder': 'Enter your phone number', 'class': 'form-control'})
    )
    shipping_address = forms.CharField(
        required=True,
        widget=forms.TextInput(attrs={'placeholder': '1234 Main St', 'class': 'form-control'})
    )
    shipping_address2 = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Apartment or suite', 'class': 'form-control'})
    )
    shipping_zip = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Zip code', 'class': 'form-control'})
    )
    shipping_country = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Country', 'class': 'form-control'})
    )
    shipping_thana = forms.ChoiceField(  # Changed to dynamic choices
        choices=[],
        required=True,
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'shipping_thana'})
    )
    billing_address = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': '1234 Main St', 'class': 'form-control'})
    )
    billing_address2 = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Apartment or suite', 'class': 'form-control'})
    )
    billing_zip = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Zip code', 'class': 'form-control'})
    )
    billing_country = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Country', 'class': 'form-control'})
    )
    billing_thana = forms.ChoiceField(
        choices=[("", "Select Thana")],
        required=False,
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'billing_thana'})
    )
    same_billing_address = forms.BooleanField(
        required=False,
        label="Same as billing address",
        help_text="Check if the shipping address is the same as the billing address."
    )
    use_default_shipping = forms.BooleanField(required=False)
    use_default_billing = forms.BooleanField(required=False)
    payment_option = forms.ChoiceField(
        widget=forms.RadioSelect,
        choices=PAYMENT_CHOICES,
        label="Choose a payment method"
    )
    bikash_transaction_id = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Bikash Transaction ID', 'class': 'form-control'}),
        label='Bikash Transaction ID'
    )
    nagad_transaction_id = forms.CharField(
        max_length=50,
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Nagad Transaction ID', 'class': 'form-control'}),
        label='Nagad Transaction ID'
    )
    district = forms.ChoiceField(
        choices=DISTRICT_CHOICES,
        required=True,
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'district'})
    )

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)

        # Initialize thana choices based on district
        district = self.data.get('district', '') if self.is_bound else self.initial.get('district', '')
        if district:
            self.fields['shipping_thana'].choices = [
                (t, t) for t in DISTRICT_THANA_MAPPING.get(district, [])
            ]

    def clean_phone_number(self):
        phone_number = self.cleaned_data.get('phone_number')
        validate_phone_number(phone_number)
        return phone_number

    def set_thana_choices(self, district):
        thanas = DISTRICT_THANA_MAPPING.get(district, [])
        self.fields['shipping_thana'].choices = [(t, t) for t in thanas]
        self.fields['billing_thana'].choices = [(t, t) for t in thanas]

    def clean(self):
        cleaned_data = super().clean()
        district = cleaned_data.get('district')
        thana = cleaned_data.get('shipping_thana')

        if district and thana:
            valid_thanas = DISTRICT_THANA_MAPPING.get(district, [])
            if thana not in valid_thanas:
                self.add_error('shipping_thana', 'Invalid thana for selected district')

        return cleaned_data

class CouponForm(forms.Form):
    code = forms.CharField(widget=forms.TextInput(attrs={
        'class': 'form-control',
        'placeholder': 'Promo code',
        'aria-label': 'Recipient\'s username',
        'aria-describedby': 'basic-addon2'
    }))

class RefundForm(forms.Form):
    ref_code = forms.CharField()
    message = forms.CharField(widget=forms.Textarea(attrs={
        'rows': 4
    }))
    email = forms.EmailField()

class PaymentForm(forms.Form):
    stripeToken = forms.CharField(required=False)
    save = forms.BooleanField(required=False)
    use_default = forms.BooleanField(required=False)

class JobApplicationForm(forms.ModelForm):
    class Meta:
        model = JobApplication
        fields = ['full_name', 'email', 'phone_number', 'portfolio_url', 'cover_letter', 'resume']
class TrackingForm(forms.Form):
    tracking_code = forms.CharField(
        max_length=50,
        required=True,
        widget=forms.TextInput(attrs={'placeholder': 'Enter Tracking Code', 'class': 'form-control'})
    )