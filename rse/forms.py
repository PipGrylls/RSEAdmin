from django import forms
from datetime import datetime, timedelta
from django.contrib.auth.forms import UserCreationForm, UserChangeForm

from .models import *


class DateRangeField(forms.Field):
    """
    Class is used to extend a text field by being able to parse the text and extract the date ranges 
    init function used to store min and max date for future use without querying database
    If validation fails then min max date range is returned
    """
    
    def __init__(self, *args,**kwargs):
        if not 'min_date' in kwargs:
            raise TypeError("DateRangeField missing required argument: 'min_date'")
        if not 'min_date' in kwargs:
            raise TypeError("DateRangeField missing required argument: 'min_date'")
        self.min_date = kwargs.pop('min_date')
        self.max_date = kwargs.pop('max_date')
        super(DateRangeField, self).__init__(*args,**kwargs)

    
    def to_python(self, value):
        # if not value then get min and max date
        if not value:
            return [self.min_date,self.max_date]
		
        # create a list of date items (one for start and one for until)
        fromuntil = value.split(' - ')
        if len(fromuntil) != 2:
            return [self.min_date,self.max_date]
        try:
            date_from = datetime.strptime(fromuntil[0], '%d/%m/%Y').date()
            date_until = datetime.strptime(fromuntil[1], '%d/%m/%Y').date()
        except ValueError:
            return [self.min_date,self.max_date]
        return [date_from, date_until]

    def validate(self, value):
        if len(value) != 2:
            forms.ValidationError('Date range is in wrong format')
            
            
            
class FilterDateRangeForm(forms.Form):
    """
    Class represents a date range field using the javascript daterangepicker library 
    It is specific to the RSEAdmin tool as it enables min and max allocated dates to be queries
    Property functions are used to be able to obtain date ranges without cluttering views
    """

    min_date = RSEAllocation.min_allocation_start()
    max_date = RSEAllocation.max_allocation_end()
    
    
    # Use custom date range field
    filter_range = DateRangeField(label='Date Range', widget=forms.TextInput(attrs={'class' : 'form-control pull-right'}) , min_date=min_date, max_date=max_date)
 
    @property
    def from_date(self):
        return self.cleaned_data["filter_range"][0]
        
    @property
    def until_date(self):
        return self.cleaned_data["filter_range"][1]
        
    @property 
    def years(self):
        return FinancialYear.objects.all()
        
        
        
        
class ProjectTypeForm(forms.Form):
    """
    Class represents a filter form for filtering by date range and service type used by many views which display multiple project views.
    Extends the filter range form by adding type and status fields
    """

    type = forms.ChoiceField(choices = (('S', 'Service'),('A', 'Allocated')), widget=forms.Select(attrs={'class' : 'form-control pull-right'}))
    

        
class FilterProjectForm(FilterDateRangeForm):
    """
    Class represents a filter form for filtering by date range and service type used by many views which display multiple project views.
    Extends the filter range form by adding type and status fields
    """

    status = forms.ChoiceField(choices = (('A', 'All'),) + Project.STATUS_CHOICES, widget=forms.Select(attrs={'class' : 'form-control pull-right'}))
    # Type cant be filtered at database level as it is a property
    #type = forms.ChoiceField(choices = (('A', 'All'), ('F', 'Allocated'), ('S', 'Service')), widget=forms.Select(attrs={'class' : 'form-control pull-right'}))
      
    
class ProjectAllocationForm(forms.ModelForm):
    """
    Form for adding and editing allocations within a project. Uses model form base type.
    Sets the start and end day of the allocation as follows
    - Start day is start of project
    - End day is start day plus remaining commitment to the project (by calculating sum of already committed hours)
    """
    
    # Fields are created manually to set the date input format
    start =  forms.DateField(widget=forms.DateInput(format = ('%d/%m/%Y'), attrs={'class' : 'form-control'}), input_formats=('%d/%m/%Y',))
    end = forms.DateField(widget=forms.DateInput(format = ('%d/%m/%Y'), attrs={'class' : 'form-control'}), input_formats=('%d/%m/%Y',))
    
    def __init__ (self, *args, **kwargs):
        """ Set the initial data """
        if not 'project' in kwargs:
            raise TypeError("ProjectAllocationForm missing required argument: 'project'")
        project = self.user = kwargs.pop('project', None)
        # call super 
        super(ProjectAllocationForm, self).__init__(*args, **kwargs)
        
        # do stuff with project to set the initial data
        self.fields['percentage'].initial = project.fte
        self.fields['start'].initial = datetime.strftime(project.start, "%d/%m/%Y")
        # remaining days must be rounded to whole days
        self.fields['end'].initial = datetime.strftime(project.start + timedelta(days=round(project.remaining_days_at_fte)), "%d/%m/%Y")

    
    class Meta:
        model = RSEAllocation
        fields = ['rse', 'percentage','start', 'end']
        widgets = {
            'rse': forms.Select(attrs={'class' : 'form-control'}),
            'percentage': forms.NumberInput(attrs={'class' : 'form-control'}),
            'project': forms.HiddenInput(),
        }
        
   
    
    def clean(self):
        cleaned_data=super(ProjectAllocationForm, self).clean()
        errors = {}
        
        # Validation checks that the dates are correct (no need to raise errors if fiedls are empty as they are required so superclass will have done this)
        if cleaned_data['start'] and cleaned_data['end']:
            if cleaned_data['start'] > cleaned_data['end'] :
                errors['end'] = ('Allocation end date can not be before start date')
        
        if errors:
            raise ValidationError(errors)
    

class AllocatedProjectForm(forms.ModelForm):    
    """
    Class for creation and editing of a project
    """
    
    # Fields are created manually to set the date input format
    start =  forms.DateField(widget=forms.DateInput(format = ('%d/%m/%Y'), attrs={'class' : 'form-control'}), input_formats=('%d/%m/%Y',))
    end = forms.DateField(widget=forms.DateInput(format = ('%d/%m/%Y'), attrs={'class' : 'form-control'}), input_formats=('%d/%m/%Y',))
    
    class Meta:
        model = AllocatedProject
        fields = ['proj_costing_id', 'name', 'description', 'client', 'internal', 'start', 'end', 'status', 'percentage', 'overheads', 'salary_band', 'created', 'creator']
        widgets = {
            'proj_costing_id': forms.TextInput(attrs={'class' : 'form-control'}),
            'name': forms.TextInput(attrs={'class' : 'form-control'}),
            'description': forms.Textarea(attrs={'class' : 'form-control'}),
            'client': forms.Select(attrs={'class' : 'form-control'}),
            'internal': forms.CheckboxInput(),
            'status': forms.Select(choices = Project.STATUS_CHOICES, attrs={'class' : 'form-control pull-right'}),
            'percentage': forms.NumberInput(attrs={'class' : 'form-control'}),
            'overheads': forms.Select(choices = AllocatedProject.OVERHEAD_CHOICES, attrs={'class' : 'form-control pull-right'}),
            'salary_band': forms.Select(attrs={'class' : 'form-control'}),
            'creator': forms.HiddenInput(),
            'created': forms.HiddenInput(),
        }
        
    def clean(self):
        cleaned_data=super(AllocatedProjectForm, self).clean()
        errors = {}
        
        # Validation checks that the dates are correct (no need to raise errors if fields are empty as they are required so superclass will have done this)
        if cleaned_data['start'] and cleaned_data['end']:
            if cleaned_data['start'] > cleaned_data['end'] :
                errors['end'] = ('Project end date can not be before start date')
        
        if errors:
            raise ValidationError(errors)

class ServiceProjectForm(forms.ModelForm):    
    """
    Class for creation and editing of a project
    """
    
    # Fields are created manually to set the date input format
    start =  forms.DateField(widget=forms.DateInput(format = ('%d/%m/%Y'), attrs={'class' : 'form-control'}), input_formats=('%d/%m/%Y',))
    end = forms.DateField(widget=forms.DateInput(format = ('%d/%m/%Y'), attrs={'class' : 'form-control'}), input_formats=('%d/%m/%Y',))
    
    class Meta:
        model = ServiceProject
        fields = ['proj_costing_id', 'name', 'description', 'client', 'internal', 'start', 'end', 'status', 'days', 'rate', 'charged', 'created', 'creator']
        widgets = {
            'proj_costing_id': forms.TextInput(attrs={'class' : 'form-control'}),
            'name': forms.TextInput(attrs={'class' : 'form-control'}),
            'description': forms.Textarea(attrs={'class' : 'form-control'}),
            'client': forms.Select(attrs={'class' : 'form-control'}),
            'internal': forms.CheckboxInput(),
            'status': forms.Select(choices = Project.STATUS_CHOICES, attrs={'class' : 'form-control pull-right'}),
            'days': forms.NumberInput(attrs={'class' : 'form-control'}),
            'rate': forms.NumberInput(attrs={'class' : 'form-control'}),
            'charged': forms.CheckboxInput(),
            'creator': forms.HiddenInput(),
            'created': forms.HiddenInput(),
        }
        
    def clean(self):
        cleaned_data=super(ServiceProjectForm, self).clean()
        errors = {}
        
        # Validation checks that the dates are correct (no need to raise errors if fields are empty as they are required so superclass will have done this)
        if cleaned_data['start'] and cleaned_data['end']:
            if cleaned_data['start'] > cleaned_data['end'] :
                errors['end'] = ('Project end date can not be before start date')
        
        if errors:
            raise ValidationError(errors)
                
            
class ClientForm(forms.ModelForm):    
    """
    Class for creation and editing of a client
    """
    class Meta:
        model = Client
        fields = ['name', 'department', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class' : 'form-control'}),
            'department': forms.TextInput(attrs={'class' : 'form-control'}),
            'description': forms.Textarea(attrs={'class' : 'form-control'}),    
        }
        

class UserTypeForm(forms.Form):
    """
    Class represents a filter form for filtering by date range and service type used by many views which display multiple project views.
    Extends the filter range form by adding type and status fields
    """

    user_type = forms.ChoiceField(choices = (('A', 'Administrator'),('R', 'RSE')), widget=forms.Select(attrs={'class' : 'form-control pull-right'}))
    

  
class NewUserForm(UserCreationForm):    
    """ Class for creating a new user """
    
    # Field to allow user to be an admin user
    is_admin = forms.BooleanField(initial=False, required=False)

    class Meta:
        model = User
        fields = UserCreationForm.Meta.fields + ('first_name', 'last_name', 'email')
        widgets = {
            'first_name': forms.TextInput(attrs={'class' : 'form-control'}),
            'last_name': forms.TextInput(attrs={'class' : 'form-control'}),
            'email': forms.EmailInput(attrs={'class' : 'form-control'}),
        }
 
    def __init__(self, *args, **kwargs):
        """ Override init to customise the UserCreationForm widget class appearance """
        super(NewUserForm, self).__init__(*args, **kwargs)
        
        # set html attributes of fields in parent form
        self.fields['username'].widget.attrs['class'] = 'form-control'
        self.fields['password1'].widget.attrs['class'] = 'form-control'
        self.fields['password2'].widget.attrs['class'] = 'form-control'
        for fieldname in ['username', 'password1', 'password2']:
            self.fields[fieldname].help_text = None
    
 
    def save(self, commit=True):
        """ Override save to make user a superuser """
        user = super(NewUserForm, self).save(commit=False)
        user.set_password(self.cleaned_data["password1"])
        # make an admin if checked
        if self.cleaned_data["is_admin"]:
            user.is_superuser = True
        # commit
        if commit:
            user.save()
        return user
        
class EditUserForm(UserChangeForm):    
    """ Class for creating a new user """
    
    # Field to allow user to be an admin user
    is_admin = forms.BooleanField(initial=False, required=False)
 
    def __init__(self, *args, **kwargs):
        """ Override init to customise the UserCreationForm widget class appearance """
        super(EditUserForm, self).__init__(*args, **kwargs)
        
        # if super user then set the is_admin initial value
        if self.instance.is_superuser:
            self.fields['is_admin'].initial = True
            
    
    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email')
        widgets = {
            'username': forms.TextInput(attrs={'class' : 'form-control'}),
            'first_name': forms.TextInput(attrs={'class' : 'form-control'}),
            'last_name': forms.TextInput(attrs={'class' : 'form-control'}),
            'email': forms.EmailInput(attrs={'class' : 'form-control'}),
        }
 
    def save(self, commit=True):
        """ Override save to make user a superuser """
        user = super(EditUserForm, self).save(commit=False)
        # make an admin if checked
        if self.cleaned_data["is_admin"]:
            user.is_superuser = True
        # commit
        if commit:
            user.save()
        return user
    
class NewRSEUserForm(forms.ModelForm):    
    """
    Class for creation and editing of a client
    """
    
    employed_from =  forms.DateField(widget=forms.DateInput(format = ('%d/%m/%Y'), attrs={'class' : 'form-control'}), input_formats=('%d/%m/%Y',))
    employed_until =  forms.DateField(widget=forms.DateInput(format = ('%d/%m/%Y'), attrs={'class' : 'form-control'}), input_formats=('%d/%m/%Y',))
    
    class Meta:
        model = RSE
        fields = ['employed_from', 'employed_until']
        
class NewSalaryBandForm(forms.ModelForm):
    """
    Class represents a form for creating a new salary band with a given year
    """
    
    def __init__(self, *args, **kwargs):
        # if no instance then we expect a year to set as initial value
        if not 'instance' in kwargs:
            if not 'year' in kwargs:
                raise TypeError("NewSalaryBandForm requires either an 'instance' or a 'year'")
            year = kwargs.pop('year', None)
        else:
            year = instance.year
        super(NewSalaryBandForm, self).__init__(*args, **kwargs)
        self.fields['year'].initial = year

    class Meta:
        model = SalaryBand
        fields = ['grade', 'grade_point', 'year', 'salary', 'increments']
        widgets = {
            'grade': forms.NumberInput(attrs={'class' : 'form-control'}),
            'grade_point': forms.NumberInput(attrs={'class' : 'form-control'}),
            'year': forms.HiddenInput(),
            'salary': forms.NumberInput(attrs={'class' : 'form-control'}),
            'increments': forms.CheckboxInput(),
        }


  