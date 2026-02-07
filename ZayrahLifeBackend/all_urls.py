# ZayrahLifeBackend/all_urls.py
from user_api import urls as user_urls
from customer_api import urls as customer_urls
from category_api import urls as category_urls
from supplier_api import urls as supplier_api
from product_api import urls as product_api


urlpatterns = []

urlpatterns += user_urls.urlpatterns
urlpatterns += customer_urls.urlpatterns
urlpatterns += category_urls.urlpatterns
urlpatterns += supplier_api.urlpatterns
urlpatterns += product_api.urlpatterns
