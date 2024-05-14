from datetime import datetime, timedelta
from typing import Dict

from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.views.generic.edit import DeleteView
from django.urls import reverse_lazy
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect, Http404, HttpResponseServerError
from django.shortcuts import get_object_or_404, render
from django.db.models import Max, Min, ProtectedError 
from django.db import IntegrityError
from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib import messages
from django.contrib.auth.forms import AdminPasswordChangeForm
from django.http import JsonResponse
from django.conf import settings


from rse.models import *
from rse.forms import *

############
### RSEs ###
############
   

@login_required
def rse(request: HttpRequest, rse_username: str) -> HttpResponse:
    # Get the user
    user = get_object_or_404(User, username=rse_username)

    # Dict for view
    view_dict = {}  # type: Dict[str, object]

    # Get RSE if exists
    rse = get_object_or_404(RSE, user=user)
    view_dict['rse'] = rse

    # Construct q query and check the project filter form
    q = Q()
    from_date = None
    until_date = None
    if request.method == 'GET':
        form = FilterProjectForm(request.GET)
        if form.is_valid():
            filter_range = form.cleaned_data["filter_range"]
            from_date = filter_range[0]
            q &= Q(end__gte=from_date)
            until_date = filter_range[1]
            q &= Q(start__lte=until_date)

            # apply status type query
            status = form.cleaned_data["status"]
            if status in 'PRFX':
                q &= Q(project__status=status)
            elif status == 'L':
                q &= Q(project__status='F')|Q(project__status='R')
            elif status == 'U':
                q &= Q(project__status='F')|Q(project__status='R')|Q(project__status='P')
    else:
        form = FilterProjectForm()
    

    # Get RSE allocations grouped by RSE based off Q filter and save the form
    q &= Q(rse=rse)
    allocations = RSEAllocation.objects.filter(q)
    view_dict['allocations'] = allocations
    view_dict['form'] = form
    
    # RSE in dictinary with allocations
    rses = {}
    rses[rse] = allocations
    view_dict['rses'] = rses

    # Get the commitment summary (date, effort, RSEAllocation)
    if allocations:
        view_dict['commitment_data'] = [(rse, RSEAllocation.commitment_summary(allocations, from_date, until_date))]
	
    return render(request, 'rse.html', view_dict)

@login_required
def rseid(request: HttpRequest, rse_id: int) -> HttpResponse:
    r = get_object_or_404(RSE, id=rse_id)
    
    return rse(request, r.user.username)

@login_required
def rses(request: HttpRequest) -> HttpResponse:
    """
    Filters to be handled client side with DataTables
    """
    
    rses = RSE.objects.all()

    # calculate grade point (only displayed for superusers)
    for rse in rses:
        try:
            rse.grade = rse.futureSalaryBand(date=timezone.now().date()).short_str
        except:
            rse.grade = "No Data"
    
    return render(request, 'rses.html', { "rses": rses })


@login_required
def commitment(request: HttpRequest) -> HttpResponse:

    # Dict for view
    view_dict = {}  # type: Dict[str, object]

    # Construct q query and check the project filter form
    q = Q()
    from_date = None
    until_date = None
    if request.method == 'GET':
        form = FilterProjectForm(request.GET)
        if form.is_valid():
            filter_range = form.cleaned_data["filter_range"]
            from_date = filter_range[0]
            q &= Q(end__gte=from_date)
            until_date = filter_range[1]
            q &= Q(start__lte=until_date)

            # apply status type query
            status = form.cleaned_data["status"]
            if status in 'PRFX':
                q &= Q(project__status=status)
            elif status == 'L':
                q &= Q(project__status='F')|Q(project__status='R')
            elif status == 'U':
                q &= Q(project__status='F')|Q(project__status='R')|Q(project__status='P')
    else:
        form = FilterProjectForm()
        
    # Get RSE allocations grouped by RSE based off Q filter and save the form
    allocations = RSEAllocation.objects.filter(q)
    view_dict['form'] = form
        
    # Get unique RSE ids allocated to project and build list of (RSE, [RSEAllocation]) objects for commitment graph
    allocation_unique_rses = allocations.values('rse').distinct()
    commitment_data = []
    rse_allocations = {}
    for a in allocation_unique_rses:
        r_a = allocations.filter(rse__id=a['rse'])
        rse = RSE.objects.get(id=a['rse'])
        rse_allocations[rse] = r_a
        commitment_data.append((rse, RSEAllocation.commitment_summary(r_a, from_date, until_date)))
    view_dict['commitment_data'] = commitment_data
    view_dict['rse_allocations'] = rse_allocations
	

    return render(request, 'commitments.html', view_dict)

