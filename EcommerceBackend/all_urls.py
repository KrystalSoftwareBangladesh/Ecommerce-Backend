# EcommerceBackend/all_urls.py
from user_api import urls as user_urls
from customer_api import urls as customer_urls
from account_api import urls as account_urls
from transaction_api import urls as transaction_urls
from category_api import urls as category_urls
from supplier_api import urls as supplier_urls
from product_api import urls as product_urls
from inventory_api import urls as inventory_urls
from purchase_api import urls as purchase_urls
from sale_api import urls as sale_urls
from origin_api import urls as origin_urls
from review_api import urls as review_urls
from meta_api import urls as meta_urls
from wishlist_api import urls as wishlist_urls
from cart_api import urls as cart_urls
from content_security_api import urls as content_security_urls


urlpatterns = []

urlpatterns += user_urls.urlpatterns
urlpatterns += customer_urls.urlpatterns
urlpatterns += account_urls.urlpatterns
urlpatterns += transaction_urls.urlpatterns
urlpatterns += category_urls.urlpatterns
urlpatterns += supplier_urls.urlpatterns
urlpatterns += product_urls.urlpatterns
urlpatterns += inventory_urls.urlpatterns
urlpatterns += purchase_urls.urlpatterns
urlpatterns += sale_urls.urlpatterns
urlpatterns += origin_urls.urlpatterns
urlpatterns += review_urls.urlpatterns
urlpatterns += meta_urls.urlpatterns
urlpatterns += wishlist_urls.urlpatterns
urlpatterns += cart_urls.urlpatterns
urlpatterns += content_security_urls.urlpatterns
