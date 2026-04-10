from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.models import User

from .models import UserProfile


class SignupForm(UserCreationForm):
    email = forms.EmailField()
    first_name = forms.CharField(max_length=150)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        placeholders = {
            "first_name": "Your name",
            "username": "Username",
            "email": "you@example.com",
            "password1": "Create password",
            "password2": "Confirm password",
        }
        for name, field in self.fields.items():
            field.widget.attrs.update({"placeholder": placeholders.get(name, field.label)})

    class Meta:
        model = User
        fields = ("first_name", "username", "email", "password1", "password2")


class StyledAuthenticationForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput())
    password = forms.CharField(widget=forms.PasswordInput())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update({"placeholder": "Username"})
        self.fields["password"].widget.attrs.update({"placeholder": "Password"})


class ParentContactForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ("parent_whatsapp_number", "parent_updates_enabled")
        widgets = {
            "parent_whatsapp_number": forms.TextInput(
                attrs={"placeholder": "Parent phone number with country code"}
            ),
        }

    def clean_parent_whatsapp_number(self):
        raw_value = str(self.cleaned_data["parent_whatsapp_number"]).strip()
        value = "".join(char for char in raw_value if char.isdigit() or char == "+")
        digits_only = "".join(char for char in value if char.isdigit())
        if value and not value.startswith("+"):
            if len(digits_only) == 10:
                value = f"+91{digits_only}"
            else:
                value = f"+{digits_only}"
        if self.cleaned_data.get("parent_updates_enabled") and not value:
            raise forms.ValidationError("Add a parent phone number to enable updates.")
        return value
