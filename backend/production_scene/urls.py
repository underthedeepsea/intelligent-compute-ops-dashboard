from django.urls import path
from . import views
urlpatterns=[path('hardware',views.hardware_inventory),path('topology',views.topology),path('catalog',views.catalog),path('source',views.source_packet),path('imports/<str:action>',views.imports),path('replay/dataset',views.dataset),path('replay/frame',views.replay_frame),path('live/<str:kind>',views.live)]
