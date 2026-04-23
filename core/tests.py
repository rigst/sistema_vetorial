from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class AuthFlowTests(TestCase):
    def test_login_required_redirects_home(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_password_reset_form_renders(self):
        user = get_user_model().objects.create_user(
            username="auth-user",
            email="auth@example.com",
            password="senha123",
        )
        response = self.client.get(reverse("password_reset"))
        self.assertEqual(response.status_code, 200)
