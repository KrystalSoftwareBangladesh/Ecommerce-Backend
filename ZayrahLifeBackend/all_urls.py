# ZayrahLifeBackend/all_urls.py
from user_api import urls as user_urls
from customer_api import urls as customer_urls
from category_api import urls as category_urls


urlpatterns = []

urlpatterns += user_urls.urlpatterns
urlpatterns += customer_urls.urlpatterns
urlpatterns += category_urls.urlpatterns
