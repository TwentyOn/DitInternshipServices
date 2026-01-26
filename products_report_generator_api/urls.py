from django.urls import path
from . import views

urlpatterns = [
    path('reports/', views.Reports.as_view()),
    path('reports/create_data/', views.CreateReportData.as_view()),
    path('reports/<int:report_id>/', views.ReportToEdit.as_view()),
    path('products/', views.Products.as_view()),
    path('products/<int:product_id>/', views.ProductToEdit.as_view()),
    path('campaigns/', views.Campaigns.as_view()),
    path('campaigns/<int:campaign_id>/', views.CampaignToEdit.as_view()),
    path('actions_handbooks/', views.ActionsHandbooks.as_view()),
    path('actions_handbooks/<int:action_handbook_id>/', views.ActionHandbookToEdit.as_view()),
    path('goals_handbooks/', views.GoalsHandbooks.as_view()),
    path('goals_handbooks/<int:goal_handbook_id>/', views.GoalHandbookToEdit.as_view()),
    path('ym/goals/<int:product_id>/', views.YMGoals.as_view()),
    path('yd/campaigns/<int:product_id>/', views.YDCampaigns.as_view()),
    path('products/dropdown_list/', views.ProductsDropdownList.as_view())
]
