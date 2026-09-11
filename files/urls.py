from django.urls import path
from . import views

app_name = 'files'

urlpatterns = [
    # Global entry router
    path('', views.files_router, name='files_router'),

    # Workspace-scoped primary views
    path('w/<slug:slug>/', views.files_home, name='files_home'),
    path('w/<slug:slug>/folders/<uuid:folder_id>/', views.folder_view, name='folder_view'),
    path('w/<slug:slug>/<uuid:file_id>/', views.file_detail, name='file_detail'),
    path('w/<slug:slug>/upload/', views.file_upload, name='file_upload'),
    path('w/<slug:slug>/recent/', views.recent_files, name='recent_files'),
    path('w/<slug:slug>/shared/', views.shared_files, name='shared_files'),

    # File & Folder operations
    path('w/<slug:slug>/<uuid:file_id>/download/', views.file_download, name='file_download'),
    path('w/<slug:slug>/<uuid:file_id>/star/', views.file_star_toggle, name='file_star_toggle'),
    path('w/<slug:slug>/folders/<uuid:folder_id>/star/', views.folder_star_toggle, name='folder_star_toggle'),
    path('w/<slug:slug>/folders/create/', views.folder_create, name='folder_create'),
    path('w/<slug:slug>/folders/<uuid:folder_id>/delete/', views.folder_delete, name='folder_delete'),
    path('w/<slug:slug>/<uuid:file_id>/rename/', views.file_rename, name='file_rename'),
    path('w/<slug:slug>/<uuid:file_id>/move/', views.file_move, name='file_move'),
    path('w/<slug:slug>/<uuid:file_id>/delete/', views.file_delete, name='file_delete'),
    path('w/<slug:slug>/<uuid:file_id>/restore/', views.file_restore, name='file_restore'),
    path('w/<slug:slug>/<uuid:file_id>/share/', views.file_share, name='file_share'),
    path('w/<slug:slug>/<uuid:file_id>/unshare/<uuid:share_id>/', views.file_unshare, name='file_unshare'),
    path('w/<slug:slug>/<uuid:file_id>/comment/', views.file_comment_create, name='file_comment_create'),
    path('w/<slug:slug>/<uuid:file_id>/version/', views.file_version_upload, name='file_version_upload'),

    # People Search API for sharing modal (strictly search-first)
    path('w/<slug:slug>/api/search-members/', views.member_search_api, name='member_search_api'),
]
