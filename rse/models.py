from __future__ import annotations
from datetime import datetime, date, timedelta
from django.utils import timezone
from math import floor
from typing import Optional, Dict
from decimal import Decimal
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db.utils import OperationalError, ProgrammingError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import ugettext_lazy as _
from polymorphic.models import PolymorphicModel
from django.db.models import Max, Min, QuerySet
from typing import Iterator, Union, TypeVar, Generic
import itertools as it
from copy import deepcopy
from django.conf import settings

# import the logging library for debugging
import logging

# Get an instance of a logger
logger = logging.getLogger(__name__)

# Class for typed query set to be used in type hints
T = TypeVar("T")


class TypedQuerySet(Generic[T]):
    """
    Django type hints for query sets are not typed (not very useful).
    The following class can eb used to provide type information (see: https://stackoverflow.com/a/54797356)
    """
    def __iter__(self) -> Iterator[Union[T, QuerySet]]:
        pass


# Start of the models
class Client(models.Model):
    """
    Client represents a client of RSE work. Usually a named academic of university staff member in a given department, professional service or research institute.
    """
    name = models.CharField(max_length=100)         # contact name (usually academic)
    department = models.CharField(max_length=100)   # university department
    description = models.TextField(blank=True)

    @property
    def total_projects(self) -> int:
        """ Returns the number of projects associated with this client """
        return Project.objects.filter(client=self).count()

    @property
    def funded_projects(self) -> int:
        """ Returns the number of active projects associated with this client """
        return Project.objects.filter(client=self, status=Project.FUNDED).count()

    @property
    def funded_projects_percent(self) -> float:
        """ Returns the number percentage of active projects associated with this client """
        if self.total_projects > 0:
            return self.funded_projects / self.total_projects * 100.0 if self.total_projects != 0 else 100
        else:
            return 0

    def __str__(self) -> str:
        return self.name

    class Meta:
        """ Order clients by name """
        ordering = ["name"]


class RSE(models.Model):
    """
    RSE represents a RSE staff member within the RSE team
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    employed_from = models.DateField(null=False, default=datetime(2024, 1, 1))
    employed_until = models.DateField(null=False, default=datetime(2099, 1, 1))

    @property
    def current_employment(self):
        """
        Is the staff member currently employed
        """
        if not self.employed_from:
            return None
        else:
            now = timezone.now().date()
            return self.employed_from < now and self.employed_until > now

    def __str__(self) -> str:
        return f"{self.user.first_name} {self.user.last_name}"

    @property
    def current_capacity(self) -> float:
        """ Returns the current capacity of an RSE as a percentage of FTE. Only includes funded projects. """
        now = timezone.now().date()
        return sum(a.percentage for a in RSEAllocation.objects.filter(rse=self, start__lte=now, end__gt=now, project__status='F'))

    def employed_in_period(self, from_date: date, until_date: date):
        """
        Returns True is the rse employment within the specified period
        """

        if not self.employed_from:
            return False

        if self.employed_from < until_date and self.employed_until > from_date:
            return True
        else:
            return False

    @property
    def colour_rbg(self) -> Dict[str, int]:
        r = hash(self.user.first_name) % 255
        g = hash(self.user.last_name) % 255
        b = hash(self.user.first_name + self.user.last_name) % 255
        return {"r": r, "g": g, "b": b}


class Project(PolymorphicModel):
    """
    Project represents a project undertaken by RSE team.
    Projects are not abstract but should not be initialised without using either a DirectlyIncurredProject or ServiceProject (i.e. Multi-Table Inheritance). The Polymorphic django utility is used to make inheritance much cleaner.
    See docs: https://django-polymorphic.readthedocs.io/en/stable/quickstart.html
    """
    creator = models.ForeignKey(User, on_delete=models.PROTECT)
    created = models.DateTimeField()

    proj_costing_id = models.CharField(max_length=50, null=True)    # Internal URMS code
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    client = models.ForeignKey(Client, on_delete=models.PROTECT)
    internal = models.BooleanField(default=False)                    # Internal or in kind projects

    start = models.DateField()
    end = models.DateField()

    PREPARATION = 'P'
    REVIEW = 'R'
    FUNDED = 'F'
    REJECTED = 'X'
    STATUS_CHOICES = (
        (PREPARATION, 'Preparation'),
        (REVIEW, 'Review'),
        (FUNDED, 'Funded'),
        (REJECTED, 'Rejected'),
    )
    STATUS_CHOICES_TEXT_KEYS = (
        ('Preparation', 'Preparation'),
        ('Review', 'Review'),
        ('Funded', 'Funded'),
        ('Rejected', 'Rejected'),
    )
    status = models.CharField(max_length=1, choices=STATUS_CHOICES)

    SCHEDULE_ACTIVE = "Active"
    SCHEDULE_COMPLETED = "Completed"
    SCHEDULE_SCHEDULED = "Scheduled"
    SCHEDULE_CHOICES_TEXT_KEYS = (
        ('Active', 'Active'),
        ('Completed', 'Completed'),
        ('Scheduled', 'Scheduled'),
    )

    @property
    def chargeable(self):
        """ Indicates if the project is chargeable in a cost distribution. I.e. Internal projects are not chargeable and neither are non charged service projects. """
        pass

    @staticmethod
    def status_choice_keys():
        """ Returns the available choices for status field """
        return [Project.PREPARATION, Project.REVIEW, Project.FUNDED, Project.REJECTED]

    @property
    def duration(self) -> Optional[int]:
        """ Number of calendar days required to complete the project """
        """ Implemented by concrete classes """
        pass

    @property
    def working_days(self) -> Optional[int]:
        """ Number of workings days in the project """
        """ Implemented by concrete classes """
        pass
    
    def scheduled_working_days_to_today(self, rse = None) -> float:
        """ Returns the total working days of the project upto today """
        now = timezone.now().date()
        allocated_days_sum = 0
        # get allocations (all or by RSE if specified)
        if not rse:
            active = RSEAllocation.objects.filter(project=self, start__lte=now)
        else:
            active = RSEAllocation.objects.filter(project=self, rse=rse, start__lte=now)
        for a in active:
            # allocated day need to be converted into equivalent working days
            allocated_days_sum += a.working_days(self.start, now)
        
        return allocated_days_sum

    def value(self) -> Optional[int]:
        """ Implemented by concrete classes."""
        pass

    def staff_budget(self) -> float:
        """ Implemented by concrete classes."""
        pass

    def overhead_value(self, from_date: date = None, until_date: date = None, percentage: float = None) -> float:
        """ Implemented by concrete classes. """
        pass

    @property
    def type_str(self) -> str:
        """ Implemented by concrete classes """
        pass

    @property
    def is_service(self) -> bool:
        """ Implemented by concrete classes """
        pass

    @property
    def fte(self) -> int:
        """ Implemented by concrete classes """
        pass

    @property
    def project_days(self) -> float:
        """ Duration times by fte """
        return self.duration * (self.fte / 100.0)

    @property
    def committed_days(self) -> float:
        """ Returns the committed effort in days from any allocation on this project """
        return sum(a.effort for a in RSEAllocation.objects.filter(project=self))

    @property
    def remaining_days(self) -> float:
        """ Return the number of unallocated (i.e. remaining) days for project """
        return self.project_days - self.committed_days

    @property
    def remaining_days_at_fte(self) -> float:
        """ 
        Return the number of unallocated (i.e. remaining) days for project at the projects standard fte percentage
        If FTE is 0 then remaining days is 0
        """
        return self.remaining_days / self.fte * 100 if self.fte != 0 else 0

    @property
    def percent_allocated(self) -> float:
        """ 
        Gets all allocations for this project and sums FTE*days to calculate committed effort 
        If project duration is 0 then percent is 100
        """
        return round(self.committed_days / self.project_days * 100, 2) if self.project_days != 0 else 100

    @property
    def get_schedule_display(self) -> str:
        now = timezone.now().date()
        if now < self.start:
            return Project.SCHEDULE_SCHEDULED
        elif now > self.end:
            return Project.SCHEDULE_COMPLETED
        else:
            return Project.SCHEDULE_ACTIVE

    def __str__(self):
        return self.name

    def clean(self):
        if self.status != 'P' and not self.proj_costing_id:
            raise ValidationError(_('Project proj_costing_id cannot be null if the grant has passed the preparation stage.'))
        if self.start and self.end and self.end < self.start:
            raise ValidationError(_('Project end cannot be earlier than project start.'))

    @staticmethod
    def min_start_date() -> date:
        """
        Returns the first start date for all allocations (i.e. the first allocation in the database)
        It is possible that the database does not exist when this function is called in which case function returns todays date.
        """
        try:
            min_date =  Project.objects.aggregate(Min('start'))['start__min']
            if min_date is None: # i.e. table exists but no dates
                min_date = timezone.now().date()
            return min_date
        except (OperationalError, ProgrammingError):
            return timezone.now().date()

    @staticmethod
    def max_end_date() -> date:
        """
        Returns the last end date for all allocations (i.e. the last allocation end in the database)
        It is possible that the database does not exist when this function is called in which case function returns todays date.
        """
        try:
            max_date = Project.objects.aggregate(Max('end'))['end__max']
            if max_date is None: # i.e. table exists but no dates
                max_date = timezone.now().date()
            return max_date
        except (OperationalError, ProgrammingError):
            return timezone.now().date()

    @staticmethod
    def fte_days_to_working_days(fte_days: int) -> int:
        """
        This maps FTE days into a number of working days
        """
        return fte_days * settings.WORKING_DAYS_PER_YEAR / 365.0

    def staff_cost(self, from_date: date = None, until_date: date = None, rse: RSE = None, consider_internal: bool = False) -> SalaryValue:
        """
        Returns the accumulated staff costs (from allocations) over a duration (if provided) or for the full project if not
        """

        # don't consider internal projects
        if not consider_internal and self.internal:
            return SalaryValue()

        # If no time period then use defaults for project
        # then limit specified time period to allocation
        if from_date is None or from_date < self.start:
            from_date = self.start
        if until_date is None or until_date > self.end:
            until_date = self.end

        # Filter allocations by start and end date
        if rse:
            allocations = RSEAllocation.objects.filter(project=self, end__gt=from_date, start__lt=until_date, rse=rse)
        else:
            allocations = RSEAllocation.objects.filter(project=self, end__gt=from_date, start__lt=until_date)

        # Iterate allocations and calculate staff costs
        salary_cost = SalaryValue()
        for a in allocations:

            # calculate the staff cost of the RSE between the date range given the salary band at the start of the cost query
            sc = a.staff_cost(from_date, until_date)

            # append the salary costs logging costs by allocations5
            salary_cost.add_salary_value_with_allocation(allocation=a, salary_value=sc)

        return salary_cost

    @property
    def colour_rbg(self) -> Dict[str, int]:
        r = hash(self.name) % 255
        g = hash(self.start) % 255
        b = hash(self.end) % 255
        return {"r": r, "g": g, "b": b}


class DirectlyIncurredProject(Project):
    """
    DirectlyIncurredProject is a cost recovery project used to allocate an RSE for a percentage of time given the projects start and end dates
    Allocations may span beyond project start and end dates as RSE salary cost may be less than what was costed on project.
    
    This is the only project as SCRTP decided to remove the ServiceProject model.
    """
    
    percentage = models.FloatField(validators=[MinValueValidator(0), MaxValueValidator(1000)])
    """
    FTE percentage for the project. This was increased from 100 because sometimes
    there are more than 100% FTE spent on the project.
    """

    @property
    def duration(self) -> Optional[int]:
        """
        Duration is determined by start and end dates
        """
        dur = None
        if self.end and self.start:
            dur = (self.end - self.start).days
        return dur

    @property
    def working_days(self) -> Optional[int]:
        """ Number of workings days in the project """
        """ Calculated by adjusting duration by TRAC """
        return Project.fte_days_to_working_days(self.duration)* self.fte / 100.0

    @property
    def type_str(self) -> str:
        """
        Returns a plain string representation of the project type
        """
        return "Directly Incurred"

    @property
    def is_service(self) -> bool:
        """ Implemented by concrete classes """
        return False

    @property
    def fte(self) -> int:
        """ Returns the FTE equivalent for this project """
        return self.percentage


class RSEAllocationManager(models.Manager):
    """
    RSEAllocation objects are transactional in that they are never actually deleted they are just flagged as deleted
    This custom manager allows all() to return on objects which have not been flagged as deleted 
    """
    def get_queryset(self):
        return super(RSEAllocationManager, self).get_queryset().filter(deleted_date__isnull=True)

    def all(self, deleted=False):
        if deleted:
            return super(RSEAllocationManager, self).get_queryset()
        else:
            # default is to return only non deleted items
            return self.get_queryset()


class RSEAllocation(models.Model):
    """
    Defines an allocation of an RSE to project with a given percentage of time.
    RSEAllocation objects are transactional in that they are never actually deleted they are just flagged as deleted.
    """
    rse = models.ForeignKey(RSE, on_delete=models.CASCADE)
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    percentage = models.FloatField(validators=[MinValueValidator(0),
                                               MaxValueValidator(100)])
    start = models.DateField()
    end = models.DateField()

    created_date = models.DateTimeField(default=timezone.now, editable=False)
    deleted_date = models.DateTimeField(null=True, blank=True)

    objects = RSEAllocationManager()

    def __str__(self) -> str:
        return f"{self.rse} on {self.project} at {self.percentage}%"

    @property
    def duration(self):
        return (self.end - self.start).days

    @property
    def effort(self) -> float:
        """
        Returns the number of days allocated on project (multiplied by fte)
        """
        return self.duration * self.percentage / 100.0

    @property
    def project_allocation_percentage(self) -> float:
        """ Returns the percentage of this allocation from project total """
        return self.effort / self.project.project_days * 100.0 if self.project.project_days != 0 else 100

    @property
    def current_progress(self) -> float:
        """ Returns the current progress of the allocation as a percentage """
        now = timezone.now().date()

        # not started
        if self.start > now:
            return 0.0
        # completed
        elif self.end < now:
            return 100.0

        # otherwise active
        total_days = (self.end - self.start).days
        current_days = (now - self.start).days

        return float(current_days) / float(total_days) * 100 if total_days != 0 else 100

    def working_days(self, start: None, end: None) -> Optional[int]:
        """ Number of workings days in the allocation """

        # If no time period then use defaults for project
        # then limit specified time period to allocation
        if start is None or start < self.start:
            start = self.start
        if end is None or end > self.end:
            end = self.end

        # calculate timedelta in days
        duration = (end - start).days

        return Project.fte_days_to_working_days(duration) * self.percentage / 100.0

    @staticmethod
    def min_allocation_start() -> date:
        """
        Returns the first start date for all allocations (i.e. the first allocation in the database)
        It is possible that the database does not exist when this function is called in which case function returns todays date.
        """
        try:
            return RSEAllocation.objects.aggregate(Min('start'))['start__min']
        except OperationalError:
            return timezone.now().date()

    @staticmethod
    def max_allocation_end() -> date:
        """
        Returns the last end date for all allocations (i.e. the last allocation end in the database)
        It is possible that the database does not exist when this function is called in which case function returns todays date.
        """
        try:
            return RSEAllocation.objects.aggregate(Max('end'))['end__max']
        except OperationalError:
            return timezone.now().date()

    @staticmethod
    def commitment_summary(allocations: 'RSEAllocation', from_date: date = None, until_date: date = None):

        # Helpful lambda function for max where a value may be None
        # lambda function returns a if b is None or f(a,b) if b is not none
        f_bnone = lambda f, a, b: a if b is None else f(a, b)

        # Generate a list of start and end dates and store the percentage FTE effort (negative for end dates)
        starts = [[f_bnone(max, item.start, from_date), item.percentage, item] for item in allocations]
        ends = [[f_bnone(min, item.end, until_date), -item.percentage, item] for item in allocations]

        # Combine start and end dates and sort
        events = sorted(starts + ends, key=lambda x: x[0])

        # lists of unique
        unique_cumulative_allocations = []
        unique_dates = []
        unique_effort = []

        # temporary cumulative variables
        active_allocations = []
        effort = 0

        # use itertools groupby to process by unique day
        for k, g in it.groupby(events, lambda x: x[0]):

            # iterate dates (d), percentages (p), effort (e), and allocations (a) and accumulate allocations
            for d, p, a in g:  # k will be the same a d
                # add or remove allocation depending on percentage
                if p > 0:
                    active_allocations.append(a)
                if p < 0:
                    active_allocations.remove(a)

                # accumulate effort
                effort += p

            # add date to unique
            unique_dates.append(d)
            unique_effort.append(effort)
            # add list of allocations to to unique cumulative allocations (make a copy)
            unique_cumulative_allocations.append(list(active_allocations))

        # Return list of unique (date, effort, [RSEAllocation])
        return list(zip(unique_dates, unique_effort, unique_cumulative_allocations))
