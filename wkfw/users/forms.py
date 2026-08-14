from allauth.account.forms import SignupForm
from django.contrib.auth import forms as admin_forms
from django.contrib.auth import get_user_model

User = get_user_model()


class UserAdminChangeForm(admin_forms.UserChangeForm):
    class Meta(admin_forms.UserChangeForm.Meta):
        model = User


class UserAdminCreationForm(admin_forms.UserCreationForm):
    class Meta(admin_forms.UserCreationForm.Meta):
        model = User
        fields = ("username", "email")


class UserSignupForm(SignupForm):
    def save(self, request):
        return super().save(request)
