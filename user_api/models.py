from django.db import models
from django.utils.translation import gettext_lazy as _

from django.contrib.auth.models import AbstractUser, BaseUserManager  # noqa


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        print("before", email)
        email = self.normalize_email(email)
        print("after", email)
        username = extra_fields.get("username")
        print("before", username)
        if username:
            extra_fields["username"] = username.lower()
        print("after", username)

        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    ROLE_CHOICES = [
        ("OWNER", "Owner"),
        ("STAFF", "Staff"),
        ("CUSTOMER", "Customer"),
    ]
    role = models.CharField(
        max_length=20,
        choices=ROLE_CHOICES,
        default="CUSTOMER",
    )
    first_name = models.CharField(max_length=255, blank=True, null=True)
    middle_name = models.CharField(max_length=255, blank=True, null=True)
    last_name = models.CharField(max_length=255, blank=True, null=True)
    email = models.EmailField(
        _("email address"),
        blank=True,
        null=True,
        unique=True,
    )
    username = models.CharField(
        max_length=150,
        unique=True,
        error_messages={"unique": "A user with that username already exists."},
    )
    is_deleted = models.BooleanField(default=False)
    added_at = models.DateTimeField(_('Added Date Time'), auto_now_add=True,)
    updated_at = models.DateTimeField(_('Updated Date Time'), auto_now=True,)

    objects = UserManager()

    # USERNAME_FIELD = 'username'
    # USERNAME_FIELD = 'email'
    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = ["email"]
    # REQUIRED_FIELDS = ['email']
    # REQUIRED_FIELDS = []

    @property
    def full_name(self) -> str:
        return " ".join(filter(None, [
            self.first_name, self.middle_name, self.last_name
        ]))

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        return self.full_name
