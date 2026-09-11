import os
import mimetypes
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.http import (
    HttpResponse,
    JsonResponse,
    HttpResponseForbidden,
    HttpResponseBadRequest,
    Http404,
)
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import Q, Count, Sum
from django.contrib.auth import get_user_model

from workspaces.permissions import (
    workspace_member_required,
    workspace_manager_required,
    workspace_admin_required,
    get_workspace_and_membership,
)
from workspaces.models import Workspace, WorkspaceMembership, WorkspaceRole, MembershipStatus
from .models import (
    Folder,
    StoredFile,
    FileCategory,
    FileShare,
    FileShareAccess,
    FileVersion,
    FileComment,
    FileActivity,
)
from .forms import (
    FileUploadForm,
    FolderForm,
    FileEditForm,
    FileShareForm,
    FileVersionUploadForm,
)
from .services import (
    SupabaseStorageService,
    compute_sha256,
    detect_file_category,
    detect_external_provider,
    log_file_activity,
    get_workspace_storage_metrics,
    MAX_FILE_SIZE_BYTES,
)

User = get_user_model()


@login_required
def files_router(request):
    """
    Redirects user to their active workspace's files dashboard.
    """
    active_slug = request.session.get('active_workspace_slug')
    if active_slug:
        ws = Workspace.objects.filter(
            slug=active_slug,
            memberships__user=request.user,
            memberships__status=MembershipStatus.ACTIVE
        ).first()
        if ws:
            return redirect('files:files_home', slug=ws.slug)

    first_membership = WorkspaceMembership.objects.filter(
        user=request.user,
        status=MembershipStatus.ACTIVE
    ).select_related('workspace').first()

    if first_membership:
        return redirect('files:files_home', slug=first_membership.workspace.slug)

    messages.info(request, "Please select or join a workspace to access Files & Storage.")
    return redirect('workspaces:workspace_list')


@workspace_member_required
def files_home(request, slug):
    """
    1. FILES HOME (Screen 46)
    Main file-management view with metrics, quick access folders, tabs, search, and file list.
    """
    workspace = request.workspace
    user = request.user
    current_tab = request.GET.get('tab', 'all')
    category_filter = request.GET.get('category', '')
    query = request.GET.get('q', '').strip()
    sort_by = request.GET.get('sort', '-updated_at')

    metrics = get_workspace_storage_metrics(workspace, user=user)

    # Quick Access folders (up to 5 folders with file counts)
    quick_folders = Folder.objects.filter(
        workspace=workspace,
        parent__isnull=True
    ).annotate(
        items_count=Count('files', filter=Q(files__is_trashed=False))
    ).order_by('-is_starred', 'name')[:5]

    # Queryset according to selected tab
    base_qs = StoredFile.objects.filter(workspace=workspace).select_related('uploaded_by', 'folder')

    if current_tab == 'trash':
        files_qs = base_qs.filter(is_trashed=True)
    elif current_tab == 'favorites':
        files_qs = base_qs.filter(is_trashed=False, is_starred=True)
    elif current_tab == 'recent':
        files_qs = base_qs.filter(is_trashed=False).order_by('-last_accessed_at')
    elif current_tab == 'shared':
        # Files shared with current user
        shared_file_ids = FileShare.objects.filter(
            file__workspace=workspace,
            shared_with=user
        ).values_list('file_id', flat=True)
        files_qs = base_qs.filter(id__in=shared_file_ids, is_trashed=False)
    else:  # 'all'
        files_qs = base_qs.filter(is_trashed=False)

    # Category filter
    if category_filter:
        files_qs = files_qs.filter(category=category_filter)

    # Search filter
    if query:
        files_qs = files_qs.filter(
            Q(name__icontains=query) |
            Q(original_name__icontains=query) |
            Q(description__icontains=query) |
            Q(tags__icontains=query)
        )

    # Sorting
    valid_sorts = ['name', '-name', 'size_bytes', '-size_bytes', 'updated_at', '-updated_at']
    if sort_by in valid_sorts:
        files_qs = files_qs.order_by(sort_by)
    else:
        files_qs = files_qs.order_by('-updated_at')

    # Pagination
    paginator = Paginator(files_qs, 15)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # All workspace folders for move/upload modal
    all_folders = Folder.objects.filter(workspace=workspace).order_by('name')

    context = {
        'workspace': workspace,
        'metrics': metrics,
        'quick_folders': quick_folders,
        'page_obj': page_obj,
        'files': page_obj.object_list,
        'current_tab': current_tab,
        'category_filter': category_filter,
        'categories': FileCategory.choices,
        'query': query,
        'sort_by': sort_by,
        'all_folders': all_folders,
    }
    return render(request, 'files/files_home.html', context)


@workspace_member_required
def folder_view(request, slug, folder_id):
    """
    2. FOLDER VIEW (Screen 47)
    Files and subfolders inside a selected folder with breadcrumb navigation.
    """
    workspace = request.workspace
    user = request.user
    folder = get_object_or_404(Folder, id=folder_id, workspace=workspace)

    query = request.GET.get('q', '').strip()
    view_mode = request.GET.get('view', 'list')  # 'list' or 'grid'

    subfolders = folder.subfolders.annotate(
        items_count=Count('files', filter=Q(files__is_trashed=False))
    ).order_by('name')

    files_qs = folder.files.filter(is_trashed=False).select_related('uploaded_by')
    if query:
        files_qs = files_qs.filter(
            Q(name__icontains=query) |
            Q(original_name__icontains=query) |
            Q(tags__icontains=query)
        )
    files = files_qs.order_by('-updated_at')

    ancestors = folder.get_ancestors()
    all_folders = Folder.objects.filter(workspace=workspace).exclude(id=folder.id).order_by('name')

    context = {
        'workspace': workspace,
        'folder': folder,
        'ancestors': ancestors,
        'subfolders': subfolders,
        'files': files,
        'view_mode': view_mode,
        'query': query,
        'all_folders': all_folders,
    }
    return render(request, 'files/folder_view.html', context)


@workspace_member_required
def file_detail(request, slug, file_id):
    """
    3. FILE DETAILS (Screen 48)
    Interactive file preview card, metadata sidebar, and tabs (Overview, Activity, Versions, Comments, Permissions).
    """
    workspace = request.workspace
    user = request.user
    stored_file = get_object_or_404(StoredFile, id=file_id, workspace=workspace)

    # Update last accessed
    StoredFile.objects.filter(id=stored_file.id).update(
        last_accessed_at=timezone.now(),
        last_accessed_by=user
    )

    # Permission check for editing / deleting
    is_uploader = (stored_file.uploaded_by == user)
    membership = request.membership
    can_manage = membership.can_manage_content or is_uploader

    # Check if user has explicit EDIT share permission
    user_share = stored_file.shares.filter(shared_with=user).first()
    has_edit_share = user_share and (user_share.access_level == FileShareAccess.EDIT)
    can_edit = can_manage or has_edit_share

    # Previews & content
    text_preview_content = None
    if stored_file.is_text_or_code and not stored_file.is_external_link:
        try:
            content, _ = SupabaseStorageService.get_file_content(stored_file.storage_path)
            if content:
                text_preview_content = content.decode('utf-8', errors='replace')[:15000]
        except Exception:
            text_preview_content = None

    external_provider = detect_external_provider(stored_file.external_url) if stored_file.is_external_link else None

    # Related items
    activities = stored_file.activities.select_related('actor')[:25]
    versions = stored_file.versions.select_related('uploaded_by')
    comments = stored_file.comments.select_related('author')
    shares = stored_file.shares.select_related('shared_with', 'shared_by')
    all_folders = Folder.objects.filter(workspace=workspace).order_by('name')

    context = {
        'workspace': workspace,
        'file': stored_file,
        'can_manage': can_manage,
        'can_edit': can_edit,
        'is_uploader': is_uploader,
        'text_preview_content': text_preview_content,
        'external_provider': external_provider,
        'activities': activities,
        'versions': versions,
        'comments': comments,
        'shares': shares,
        'all_folders': all_folders,
    }
    return render(request, 'files/file_detail.html', context)


@workspace_member_required
def file_upload(request, slug):
    """
    4. UPLOAD FILE (Screen 49)
    Direct file upload with drag-and-drop & size validation, or external cloud link to save space.
    """
    workspace = request.workspace
    user = request.user
    preselected_folder_id = request.GET.get('folder')
    initial_data = {}
    if preselected_folder_id:
        folder = Folder.objects.filter(id=preselected_folder_id, workspace=workspace).first()
        if folder:
            initial_data['folder'] = folder

    if request.method == 'POST':
        form = FileUploadForm(workspace, request.POST, request.FILES)
        if form.is_valid():
            upload_type = form.cleaned_data['upload_type']
            custom_name = form.cleaned_data.get('name', '').strip()
            folder = form.cleaned_data.get('folder')
            description = form.cleaned_data.get('description', '').strip()
            tags = form.cleaned_data.get('tags', '').strip()

            if upload_type == 'file':
                file_obj = request.FILES['file']
                original_name = file_obj.name
                display_name = custom_name if custom_name else original_name
                size_bytes = file_obj.size
                checksum = compute_sha256(file_obj)

                mime_type, _ = mimetypes.guess_type(original_name)
                mime_type = mime_type or file_obj.content_type or 'application/octet-stream'
                category = detect_file_category(original_name, mime_type)

                # Store file using service (Supabase with local fallback)
                storage_path = SupabaseStorageService.upload_file(
                    file_obj=file_obj,
                    workspace_id=workspace.id,
                    filename=original_name,
                    content_type=mime_type
                )

                stored_file = StoredFile.objects.create(
                    workspace=workspace,
                    folder=folder,
                    uploaded_by=user,
                    name=display_name,
                    original_name=original_name,
                    storage_path=storage_path,
                    is_external_link=False,
                    mime_type=mime_type,
                    category=category,
                    size_bytes=size_bytes,
                    checksum=checksum,
                    description=description,
                    tags=tags,
                )

                # Create initial version
                FileVersion.objects.create(
                    file=stored_file,
                    version_number=1,
                    storage_path=storage_path,
                    size_bytes=size_bytes,
                    uploaded_by=user,
                    checksum=checksum,
                    note='Initial upload'
                )

                log_file_activity(stored_file, user, 'UPLOADED', f"Uploaded {original_name} ({stored_file.formatted_size})")

            else:  # 'link'
                external_url = form.cleaned_data['external_url'].strip()
                provider = detect_external_provider(external_url)
                display_name = custom_name if custom_name else f"{provider} Asset"

                stored_file = StoredFile.objects.create(
                    workspace=workspace,
                    folder=folder,
                    uploaded_by=user,
                    name=display_name,
                    original_name=display_name,
                    external_url=external_url,
                    is_external_link=True,
                    mime_type='text/uri-list',
                    category=FileCategory.URL_LINK,
                    size_bytes=0,
                    description=description,
                    tags=tags,
                )

                FileVersion.objects.create(
                    file=stored_file,
                    version_number=1,
                    external_url=external_url,
                    size_bytes=0,
                    uploaded_by=user,
                    note='Initial link added'
                )

                log_file_activity(stored_file, user, 'LINK_CREATED', f"Added external link: {external_url}")

            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    'status': 'success',
                    'file_id': str(stored_file.id),
                    'redirect_url': reverse('files:file_detail', kwargs={'slug': workspace.slug, 'file_id': stored_file.id})
                })

            messages.success(request, f"Successfully added '{stored_file.name}'.")
            if folder:
                return redirect('files:folder_view', slug=workspace.slug, folder_id=folder.id)
            return redirect('files:file_detail', slug=workspace.slug, file_id=stored_file.id)

        else:
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({'status': 'error', 'errors': form.errors}, status=400)
            messages.error(request, "Please fix the errors below to upload your file.")
    else:
        form = FileUploadForm(workspace, initial=initial_data)

    metrics = get_workspace_storage_metrics(workspace, user=user)

    context = {
        'workspace': workspace,
        'form': form,
        'metrics': metrics,
        'max_size_mb': int(MAX_FILE_SIZE_BYTES / (1024 * 1024)),
    }
    return render(request, 'files/file_upload.html', context)


@workspace_member_required
def recent_files(request, slug):
    """
    5. RECENT FILES (Screen 50)
    Files recently accessed or modified with filter tabs (All, Opened by me, Modified by me).
    """
    workspace = request.workspace
    user = request.user
    filter_tab = request.GET.get('tab', 'all')  # 'all', 'opened_by_me', 'modified_by_me'

    base_qs = StoredFile.objects.filter(
        workspace=workspace,
        is_trashed=False
    ).select_related('uploaded_by', 'folder', 'last_accessed_by')

    if filter_tab == 'opened_by_me':
        files_qs = base_qs.filter(last_accessed_by=user).order_by('-last_accessed_at')
    elif filter_tab == 'modified_by_me':
        files_qs = base_qs.filter(uploaded_by=user).order_by('-updated_at')
    else:
        files_qs = base_qs.order_by('-last_accessed_at')

    paginator = Paginator(files_qs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'workspace': workspace,
        'files': page_obj.object_list,
        'page_obj': page_obj,
        'filter_tab': filter_tab,
    }
    return render(request, 'files/recent_files.html', context)


@workspace_member_required
def shared_files(request, slug):
    """
    6. SHARED FILES (Screen 51)
    Files shared with the user or shared by the user with team members.
    """
    workspace = request.workspace
    user = request.user
    filter_tab = request.GET.get('tab', 'with_me')  # 'with_me' or 'by_me'
    query = request.GET.get('q', '').strip()

    if filter_tab == 'by_me':
        shares_qs = FileShare.objects.filter(
            file__workspace=workspace,
            file__is_trashed=False,
            shared_by=user
        ).select_related('file', 'shared_with', 'file__folder', 'file__uploaded_by')
    else:
        shares_qs = FileShare.objects.filter(
            file__workspace=workspace,
            file__is_trashed=False,
            shared_with=user
        ).select_related('file', 'shared_by', 'file__folder', 'file__uploaded_by')

    if query:
        shares_qs = shares_qs.filter(
            Q(file__name__icontains=query) |
            Q(file__original_name__icontains=query)
        )

    shares_qs = shares_qs.order_by('-created_at')
    paginator = Paginator(shares_qs, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'workspace': workspace,
        'shares': page_obj.object_list,
        'page_obj': page_obj,
        'filter_tab': filter_tab,
        'query': query,
    }
    return render(request, 'files/shared_files.html', context)


@workspace_member_required
def file_download(request, slug, file_id):
    """
    Secure server-side file download endpoint.
    Verifies workspace permissions and streams or redirects to content.
    """
    workspace = request.workspace
    stored_file = get_object_or_404(StoredFile, id=file_id, workspace=workspace)

    if stored_file.is_external_link:
        log_file_activity(stored_file, request.user, 'DOWNLOADED', 'Navigated to external link')
        return redirect(stored_file.external_url)

    content, content_type = SupabaseStorageService.get_file_content(stored_file.storage_path)
    if not content:
        messages.error(request, "File data is currently unavailable.")
        return redirect('files:file_detail', slug=workspace.slug, file_id=stored_file.id)

    log_file_activity(stored_file, request.user, 'DOWNLOADED', f"Downloaded {stored_file.original_name}")

    response = HttpResponse(content, content_type=content_type or 'application/octet-stream')
    response['Content-Disposition'] = f'attachment; filename="{stored_file.original_name}"'
    response['Content-Length'] = len(content)
    return response


@workspace_member_required
def file_star_toggle(request, slug, file_id):
    """Toggle starred status for a file."""
    workspace = request.workspace
    stored_file = get_object_or_404(StoredFile, id=file_id, workspace=workspace)
    stored_file.is_starred = not stored_file.is_starred
    stored_file.save(update_fields=['is_starred'])

    action = 'STARRED' if stored_file.is_starred else 'UNSTARRED'
    log_file_activity(stored_file, request.user, action)

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success', 'is_starred': stored_file.is_starred})

    messages.success(request, f"{'Starred' if stored_file.is_starred else 'Unstarred'} '{stored_file.name}'.")
    return redirect(request.META.get('HTTP_REFERER') or 'files:files_home', slug=workspace.slug)


@workspace_member_required
def folder_star_toggle(request, slug, folder_id):
    """Toggle starred status for a folder."""
    workspace = request.workspace
    folder = get_object_or_404(Folder, id=folder_id, workspace=workspace)
    folder.is_starred = not folder.is_starred
    folder.save(update_fields=['is_starred'])

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success', 'is_starred': folder.is_starred})

    return redirect(request.META.get('HTTP_REFERER') or 'files:files_home', slug=workspace.slug)


@workspace_member_required
def folder_create(request, slug):
    """Create a new folder or subfolder."""
    workspace = request.workspace
    if request.method == 'POST':
        form = FolderForm(workspace, request.POST)
        if form.is_valid():
            folder = form.save(commit=False)
            folder.workspace = workspace
            folder.created_by = request.user
            folder.save()
            messages.success(request, f"Folder '{folder.name}' created successfully.")
            return redirect('files:folder_view', slug=workspace.slug, folder_id=folder.id)
        else:
            messages.error(request, form.errors.get('name', ["Error creating folder."])[0])
    return redirect('files:files_home', slug=workspace.slug)


@workspace_member_required
def folder_delete(request, slug, folder_id):
    """Delete a folder and move items to root or delete."""
    workspace = request.workspace
    folder = get_object_or_404(Folder, id=folder_id, workspace=workspace)

    # RBAC: Manager, Admin, or Folder Creator
    if not (request.membership.can_manage_content or folder.created_by == request.user):
        return HttpResponseForbidden("You do not have permission to delete this folder.")

    parent_id = folder.parent_id
    folder_name = folder.name
    folder.delete()

    messages.success(request, f"Folder '{folder_name}' has been deleted.")
    if parent_id:
        return redirect('files:folder_view', slug=workspace.slug, folder_id=parent_id)
    return redirect('files:files_home', slug=workspace.slug)


@workspace_member_required
def file_rename(request, slug, file_id):
    """Rename a file or update its description/tags."""
    workspace = request.workspace
    stored_file = get_object_or_404(StoredFile, id=file_id, workspace=workspace)

    # Check edit permissions
    user_share = stored_file.shares.filter(shared_with=request.user).first()
    has_edit = user_share and user_share.access_level == FileShareAccess.EDIT
    if not (request.membership.can_manage_content or stored_file.uploaded_by == request.user or has_edit):
        return HttpResponseForbidden("You do not have permission to edit this file.")

    if request.method == 'POST':
        new_name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        tags = request.POST.get('tags', '').strip()

        if new_name:
            old_name = stored_file.name
            stored_file.name = new_name
            stored_file.description = description
            stored_file.tags = tags
            stored_file.save(update_fields=['name', 'description', 'tags', 'updated_at'])
            log_file_activity(stored_file, request.user, 'RENAMED', f"Renamed from '{old_name}' to '{new_name}'")
            messages.success(request, "File details updated successfully.")

    return redirect('files:file_detail', slug=workspace.slug, file_id=stored_file.id)


@workspace_member_required
def file_move(request, slug, file_id):
    """Move file to another folder in the workspace."""
    workspace = request.workspace
    stored_file = get_object_or_404(StoredFile, id=file_id, workspace=workspace)

    if request.method == 'POST':
        target_folder_id = request.POST.get('target_folder')
        target_folder = None
        if target_folder_id:
            target_folder = get_object_or_404(Folder, id=target_folder_id, workspace=workspace)

        dest_name = target_folder.name if target_folder else 'Root'
        stored_file.folder = target_folder
        stored_file.save(update_fields=['folder', 'updated_at'])
        log_file_activity(stored_file, request.user, 'MOVED', f"Moved file to {dest_name}")
        messages.success(request, f"Moved '{stored_file.name}' to {dest_name}.")

    return redirect(request.META.get('HTTP_REFERER') or 'files:files_home', slug=workspace.slug)


@workspace_member_required
def file_delete(request, slug, file_id):
    """Move to trash or permanently delete file."""
    workspace = request.workspace
    stored_file = get_object_or_404(StoredFile, id=file_id, workspace=workspace)

    # RBAC: Creator, Manager, or Admin
    if not (request.membership.can_manage_content or stored_file.uploaded_by == request.user):
        return HttpResponseForbidden("You do not have permission to delete this file.")

    permanent = request.POST.get('permanent') == 'true' or stored_file.is_trashed

    if permanent:
        file_name = stored_file.name
        # Delete from storage
        if stored_file.storage_path:
            SupabaseStorageService.delete_file(stored_file.storage_path)
        stored_file.delete()
        messages.success(request, f"Permanently deleted '{file_name}'.")
        return redirect('files:files_home', slug=workspace.slug)
    else:
        stored_file.is_trashed = True
        stored_file.trashed_at = timezone.now()
        stored_file.save(update_fields=['is_trashed', 'trashed_at'])
        log_file_activity(stored_file, request.user, 'TRASHED', f"Moved to trash")
        messages.success(request, f"Moved '{stored_file.name}' to Trash.")
        return redirect('files:files_home', slug=workspace.slug)


@workspace_member_required
def file_restore(request, slug, file_id):
    """Restore a trashed file."""
    workspace = request.workspace
    stored_file = get_object_or_404(StoredFile, id=file_id, workspace=workspace)

    stored_file.is_trashed = False
    stored_file.trashed_at = None
    stored_file.save(update_fields=['is_trashed', 'trashed_at'])
    log_file_activity(stored_file, request.user, 'RESTORED', 'Restored from Trash')
    messages.success(request, f"Restored '{stored_file.name}' from Trash.")
    return redirect('files:files_home', slug=workspace.slug)


@workspace_member_required
def file_share(request, slug, file_id):
    """Share file with a workspace member with VIEW or EDIT permission."""
    workspace = request.workspace
    stored_file = get_object_or_404(StoredFile, id=file_id, workspace=workspace)

    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        access_level = request.POST.get('access_level', FileShareAccess.VIEW)

        target_user = get_object_or_404(User, id=user_id)
        # Verify target user is in workspace
        is_member = WorkspaceMembership.objects.filter(
            workspace=workspace,
            user=target_user,
            status=MembershipStatus.ACTIVE
        ).exists()

        if not is_member:
            messages.error(request, "Selected user is not an active member of this workspace.")
            return redirect('files:file_detail', slug=workspace.slug, file_id=stored_file.id)

        share, created = FileShare.objects.update_or_create(
            file=stored_file,
            shared_with=target_user,
            defaults={
                'shared_by': request.user,
                'access_level': access_level
            }
        )

        log_file_activity(stored_file, request.user, 'SHARED', f"Shared with {target_user.email} ({access_level})")
        messages.success(request, f"Shared '{stored_file.name}' with {target_user.get_full_name() or target_user.email}.")

    return redirect('files:file_detail', slug=workspace.slug, file_id=stored_file.id)


@workspace_member_required
def file_unshare(request, slug, file_id, share_id):
    """Revoke sharing access for a user."""
    workspace = request.workspace
    stored_file = get_object_or_404(StoredFile, id=file_id, workspace=workspace)
    share = get_object_or_404(FileShare, id=share_id, file=stored_file)

    target_email = share.shared_with.email
    share.delete()
    log_file_activity(stored_file, request.user, 'UNSHARED', f"Revoked access for {target_email}")
    messages.success(request, f"Revoked access for {target_email}.")
    return redirect('files:file_detail', slug=workspace.slug, file_id=stored_file.id)


@workspace_member_required
def file_comment_create(request, slug, file_id):
    """Add discussion comment to a file."""
    workspace = request.workspace
    stored_file = get_object_or_404(StoredFile, id=file_id, workspace=workspace)

    if request.method == 'POST':
        text = request.POST.get('comment', '').strip()
        if text:
            FileComment.objects.create(
                file=stored_file,
                author=request.user,
                comment=text
            )
            log_file_activity(stored_file, request.user, 'COMMENTED', 'Added a discussion comment')
            messages.success(request, "Comment added.")

    return redirect('files:file_detail', slug=workspace.slug, file_id=stored_file.id)


@workspace_member_required
def file_version_upload(request, slug, file_id):
    """Upload a new version of an existing file."""
    workspace = request.workspace
    stored_file = get_object_or_404(StoredFile, id=file_id, workspace=workspace)

    if request.method == 'POST':
        note = request.POST.get('note', '').strip()
        new_version_num = stored_file.versions.count() + 1

        if stored_file.is_external_link:
            new_url = request.POST.get('external_url', '').strip()
            if new_url:
                stored_file.external_url = new_url
                stored_file.save(update_fields=['external_url', 'updated_at'])
                FileVersion.objects.create(
                    file=stored_file,
                    version_number=new_version_num,
                    external_url=new_url,
                    size_bytes=0,
                    uploaded_by=request.user,
                    note=note or f"Updated link v{new_version_num}"
                )
                log_file_activity(stored_file, request.user, 'VERSION_ADDED', f"Updated link to v{new_version_num}")
                messages.success(request, f"Updated to version {new_version_num}.")
        else:
            if 'file' in request.FILES:
                file_obj = request.FILES['file']
                if file_obj.size > MAX_FILE_SIZE_BYTES:
                    messages.error(request, "File exceeds 20 MB size limit.")
                    return redirect('files:file_detail', slug=workspace.slug, file_id=stored_file.id)

                storage_path = SupabaseStorageService.upload_file(
                    file_obj=file_obj,
                    workspace_id=workspace.id,
                    filename=file_obj.name,
                    content_type=file_obj.content_type
                )
                checksum = compute_sha256(file_obj)

                stored_file.storage_path = storage_path
                stored_file.size_bytes = file_obj.size
                stored_file.checksum = checksum
                stored_file.save(update_fields=['storage_path', 'size_bytes', 'checksum', 'updated_at'])

                FileVersion.objects.create(
                    file=stored_file,
                    version_number=new_version_num,
                    storage_path=storage_path,
                    size_bytes=file_obj.size,
                    uploaded_by=request.user,
                    checksum=checksum,
                    note=note or f"Uploaded version {new_version_num}"
                )
                log_file_activity(stored_file, request.user, 'VERSION_ADDED', f"Uploaded version {new_version_num}")
                messages.success(request, f"New version {new_version_num} uploaded successfully.")

    return redirect('files:file_detail', slug=workspace.slug, file_id=stored_file.id)


@workspace_member_required
def member_search_api(request, slug):
    """
    Search workspace members for file sharing modal.
    CRITICAL RULE:
    - Empty query = return NO users (empty list []).
    - Only return matching users after the user types a search term.
    """
    workspace = request.workspace
    query = request.GET.get('q', '').strip()

    # PEOPLE SEARCH RULE: empty search = NO users displayed
    if not query:
        return JsonResponse({'results': []})

    memberships = WorkspaceMembership.objects.filter(
        workspace=workspace,
        status=MembershipStatus.ACTIVE
    ).filter(
        Q(user__email__icontains=query) |
        Q(user__full_name__icontains=query) |
        Q(user__username__icontains=query)
    ).select_related('user').exclude(user=request.user)[:10]

    results = []
    for m in memberships:
        u = m.user
        results.append({
            'id': str(u.id),
            'full_name': u.get_full_name() or u.username,
            'email': u.email,
            'role': m.get_role_display(),
            'avatar_url': getattr(u, 'avatar_url', None) or (u.avatar.url if getattr(u, 'avatar', None) else ''),
            'initials': (u.get_full_name() or u.email)[:2].upper(),
        })

    return JsonResponse({'results': results})
