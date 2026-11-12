# cms_api/pages/templates.py
"""Code-owned page template registry (docs/cms-architecture.md 5.1).

A template only seeds an initial composition when a page is created
(AD-3); it never constrains later editing. Seeds become local
``CmsPageSection`` rows on the new page.
"""

PAGE_TEMPLATES = {
    "blank": {
        "label": "Blank",
        "sections": [],
    },
    "landing": {
        "label": "Landing",
        "sections": [
            {
                "name": "Hero banner",
                "content": [{
                    "type": "hero_banner",
                    "value": {
                        "heading": "Welcome",
                        "subheading": "",
                        "image": None,
                        "cta_label": "",
                        "cta_url": "",
                    },
                }],
            },
            {
                "name": "Rich text",
                "content": [{
                    "type": "rich_text",
                    "value": {
                        "body": "<p>Tell your story here.</p>",
                    },
                }],
            },
        ],
    },
    "about": {
        "label": "About",
        "sections": [
            {
                "name": "Heading",
                "content": [{
                    "type": "heading",
                    "value": {
                        "heading": "About us",
                        "level": "h2",
                    },
                }],
            },
            {
                "name": "Rich text",
                "content": [{
                    "type": "rich_text",
                    "value": {
                        "body": "<p>Tell your story here.</p>",
                    },
                }],
            },
        ],
    },
    "contact": {
        "label": "Contact",
        "sections": [
            {
                "name": "Contact information",
                "content": [{
                    "type": "contact_information",
                    "value": {
                        "heading": "Contact us",
                        "phone": "",
                        "email": "",
                        "address": "",
                        "working_hours": "",
                    },
                }],
            },
        ],
    },
    "campaign": {
        "label": "Campaign",
        "sections": [
            {
                "name": "Promotional banner",
                "content": [{
                    "type": "promotional_banner",
                    "value": {
                        "heading": "Special offer",
                        "subheading": "",
                        "image": None,
                        "button_label": "",
                        "button_url": "",
                    },
                }],
            },
            {
                "name": "Product slider",
                "content": [{
                    "type": "product_slider",
                    "value": {
                        "mode": "LATEST",
                        "products": [],
                        "category": None,
                        "brand": None,
                        "limit": 8,
                    },
                }],
            },
        ],
    },
}

PAGE_TEMPLATE_CHOICES = [
    (key, entry["label"]) for key, entry in PAGE_TEMPLATES.items()
]
