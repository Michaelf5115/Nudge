import uuid

from django.db import models


class Team(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.TextField()
    phone_number = models.TextField(unique=True)
    admin_phone = models.TextField(null=True, blank=True)
    admin_email = models.TextField(null=True, blank=True)
    timezone = models.TextField(default='America/New_York')
    digest_hour = models.IntegerField(default=8)
    setup_complete = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'teams'

    def __str__(self):
        return self.name


class User(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, db_column='team_id')
    name = models.TextField()
    phone_number = models.TextField()
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'users'
        unique_together = [('team', 'phone_number')]

    def __str__(self):
        return self.name


class Task(models.Model):
    STATUS_OPEN = 'open'
    STATUS_DONE = 'done'
    STATUS_BLOCKED = 'blocked'
    STATUS_CHOICES = [(STATUS_OPEN, 'Open'), (STATUS_DONE, 'Done'), (STATUS_BLOCKED, 'Blocked')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, db_column='team_id')
    owner = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='owned_tasks', db_column='owner_id',
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_tasks', db_column='created_by_id',
    )
    title = models.TextField()
    status = models.TextField(default=STATUS_OPEN, choices=STATUS_CHOICES)
    due_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = 'tasks'

    def __str__(self):
        return self.title


class Message(models.Model):
    DIRECTION_IN = 'in'
    DIRECTION_OUT = 'out'
    DIRECTION_CHOICES = [(DIRECTION_IN, 'Inbound'), (DIRECTION_OUT, 'Outbound')]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True, db_column='team_id')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, db_column='user_id')
    direction = models.TextField(choices=DIRECTION_CHOICES)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'messages'


class LLMLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True, db_column='team_id')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, db_column='user_id')
    input_tokens = models.IntegerField()
    output_tokens = models.IntegerField()
    intent = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'llm_logs'


class MagicToken(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, db_column='team_id')
    token = models.TextField(unique=True)
    used = models.BooleanField(default=False)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'magic_tokens'


class PendingInvite(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, db_column='team_id')
    phone_number = models.TextField()
    name = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'pending_invites'
        unique_together = [('team', 'phone_number')]


class Waitlist(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.TextField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'waitlist'
