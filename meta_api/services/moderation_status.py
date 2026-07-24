# meta_api/services/moderation_status.py
from EcommerceBackend.core.choices import ModerationStatus


def get_moderation_statuses():
    return [
        {
            "key": status.name,
            "value": status.value,
            "label": status.label,
        }
        for status in ModerationStatus
    ]
