# ZayrahLifeBackend/all_urls.py
from user_api import urls as user_urls
from customer_api import urls as customer_urls
from category_api import urls as category_urls
from supplier_api import urls as supplier_urls
from product_api import urls as product_urls
from inventory_api import urls as inventory_urls
from purchase_api import urls as purchase_urls


urlpatterns = []

urlpatterns += user_urls.urlpatterns
urlpatterns += customer_urls.urlpatterns
urlpatterns += category_urls.urlpatterns
urlpatterns += supplier_urls.urlpatterns
urlpatterns += product_urls.urlpatterns
urlpatterns += inventory_urls.urlpatterns
urlpatterns += purchase_urls.urlpatterns
