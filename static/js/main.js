document.addEventListener('DOMContentLoaded', function() {

    // Mobile Menu Toggle
    const menuToggle = document.getElementById('menu-toggle');
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('overlay');

    if (menuToggle && sidebar && overlay) {
        menuToggle.addEventListener('click', function() {
            sidebar.classList.toggle('sidebar-open');
            overlay.classList.toggle('active');
        });
        overlay.addEventListener('click', function() {
            sidebar.classList.remove('sidebar-open');
            overlay.classList.remove('active');
        });
    }

    // Custom Modal Logic (Alerts & Deletes)
    const modalOverlay = document.getElementById('custom-confirm-overlay');
    const modalBox = document.querySelector('#custom-confirm-overlay .modal-box');
    const modalTitle = document.querySelector('#custom-confirm-overlay .modal-title');
    const modalText = document.querySelector('#custom-confirm-overlay .modal-text');
    const modalItemName = document.getElementById('modal-item-name');
    const modalConfirmBtn = document.getElementById('modal-btn-confirm');
    const modalCancelBtn = document.getElementById('modal-btn-cancel');

    let confirmCallback = null; 

    function showConfirmModal(title, text, itemName, onConfirm) {
        modalTitle.textContent = title;
        modalText.textContent = text;
        modalItemName.textContent = `"${itemName}"`;
        modalItemName.style.display = 'block';

        modalBox.classList.remove('is-alert');
        modalConfirmBtn.textContent = 'Delete';
        modalConfirmBtn.classList.add('btn-danger');
        
        confirmCallback = onConfirm; 

        modalOverlay.style.display = 'flex';
        setTimeout(() => modalOverlay.classList.add('active'), 10);
    }
    
    function showAlertModal(title, message) {
        modalTitle.textContent = title;
        modalText.textContent = message;
        modalItemName.style.display = 'none'; 

        modalBox.classList.add('is-alert'); 
        modalConfirmBtn.textContent = 'OK'; 
        modalConfirmBtn.classList.remove('btn-danger'); 
        
        confirmCallback = null; 

        modalOverlay.style.display = 'flex';
        setTimeout(() => modalOverlay.classList.add('active'), 10);
    }

    function hideModal() {
        modalOverlay.classList.remove('active');
        setTimeout(() => {
            modalOverlay.style.display = 'none';
        }, 200);
    }

    if (modalCancelBtn) {
        modalCancelBtn.addEventListener('click', hideModal);
    }
    if (modalConfirmBtn) {
        modalConfirmBtn.addEventListener('click', () => {
            if (confirmCallback) {
                confirmCallback(); 
            }
            hideModal(); 
        });
    }


    // Calendar Initialization
    const calendarEl = document.getElementById('calendar');
    if (calendarEl) {
        const calendar = new FullCalendar.Calendar(calendarEl, {
            initialView: 'dayGridMonth',
            headerToolbar: {
                left: 'prev,next today',
                center: 'title',
                right: 'dayGridMonth,timeGridWeek,timeGridDay'
            },
            events: '/api/calendar_events',
            eventColor: '#388E3C',
            eventClick: function(info) {
                info.jsEvent.preventDefault();
                
                showConfirmModal(
                    'Confirm Deletion', 
                    'Are you sure you want to delete this task?', 
                    info.event.title, 
                    () => { 
                        const taskId = info.event.id;
                        fetch(`/api/delete_task/${taskId}`, { method: 'DELETE' })
                            .then(response => response.json())
                            .then(data => {
                                if (data.status === 'success') {
                                    info.event.remove();
                                } else {
                                    showAlertModal('Error', 'Could not delete task.');
                                }
                            })
                            .catch(error => console.error('Error deleting task:', error));
                    }
                );
            }
        });
        calendar.render();
    }

    // Add Full Schedule to Calendar
    const addScheduleBtn = document.getElementById('add-schedule-btn');
    if (addScheduleBtn) {
        addScheduleBtn.addEventListener('click', function() {
            const diagnosisId = this.dataset.diagnosisId;
            const taskRows = document.querySelectorAll('.task-row');
            const tasksToAdd = [];
            taskRows.forEach(row => tasksToAdd.push({
                date: row.dataset.date,
                task: row.dataset.task,
                details: row.dataset.details
            }));

            if (tasksToAdd.length > 0) {
                fetch('/api/add_schedule_to_calendar', { 
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        tasks: tasksToAdd,
                        diagnosis_id: diagnosisId
                    })
                })
                .then(response => response.json())
                .then(data => {
                    showAlertModal('Success', data.message);
                    if (data.status === 'success') {
                        this.textContent = 'Schedule Added!';
                        this.disabled = true;
                    }
                })
                .catch(error => console.error('Error:', error));
            }
        });
    }

    // Schedule Follow-up Button
    const scheduleFollowUpBtn = document.getElementById('schedule-follow-up-btn');
    if (scheduleFollowUpBtn) {
        scheduleFollowUpBtn.addEventListener('click', function() {
            const diagnosisId = this.dataset.diagnosisId;
            fetch(`/api/schedule_follow_up/${diagnosisId}`, { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    showAlertModal('Success', data.message);
                    if (data.status === 'success') {
                        this.textContent = 'Follow-up Scheduled!';
                        this.disabled = true;
                    }
                })
                .catch(error => console.error('Error:', error));
        });
    }

    // Toggle Task Completion on Dashboard
    const taskCheckboxes = document.querySelectorAll('.task-item input[type="checkbox"]');
    taskCheckboxes.forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            const taskId = this.dataset.taskId;
            const taskItem = this.closest('.task-item');
            fetch(`/api/toggle_task/${taskId}`, { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success') {
                        taskItem.classList.toggle('completed', data.is_completed);
                    }
                })
                .catch(error => console.error('Error toggling task:', error));
        });
    });

    // Delete Task from Dashboard
    document.querySelectorAll('.delete-task-btn').forEach(button => {
        button.addEventListener('click', function() {
            const taskId = this.dataset.taskId;
            const taskItem = this.closest('.task-item');
            const taskTitle = taskItem.querySelector('.title').textContent;

            showConfirmModal(
                'Confirm Deletion', 
                'Are you sure you want to delete this task?', 
                taskTitle, 
                () => { 
                    fetch(`/api/delete_task/${taskId}`, { method: 'DELETE' })
                        .then(response => response.json())
                        .then(data => {
                            if (data.status === 'success') {
                                taskItem.remove();
                            } else {
                                showAlertModal('Error', 'Could not delete task.');
                            }
                        })
                        .catch(error => console.error('Error deleting task:', error));
                }
            );
        });
    });

    // Delete Logbook or User Entry Confirmation (for admin)
    document.querySelectorAll('.delete-log-form').forEach(form => {
        form.addEventListener('submit', function(event) {
            event.preventDefault(); 
            
            let itemTitle = '';
            let confirmText = '';
            
            const logItem = this.closest('.log-content');
            const userItemRow = this.closest('tr');

            if (logItem) {
                itemTitle = logItem.querySelector('h3').textContent;
                confirmText = 'Are you sure you want to delete this logbook entry? All associated tasks will also be removed.';
            } else if (userItemRow) {
                itemTitle = userItemRow.querySelector('td:first-child').textContent;
                confirmText = 'Are you sure you want to delete this user? All their diagnoses and tasks will be permanently removed.';
            } else {
                itemTitle = 'this item';
                confirmText = 'Are you sure you want to delete this item?';
            }

            showConfirmModal(
                'Confirm Deletion',
                confirmText,
                itemTitle,
                () => {
                    event.target.submit(); 
                }
            );
        });
    });

    // Admin & Report Modals
    // Edit User Modal
    const editUserOverlay = document.getElementById('edit-user-overlay');
    const editUserForm = document.getElementById('edit-user-form');
    
    window.openEditUserModal = function(button) {
        const id = button.dataset.userId;
        const name = button.dataset.name;
        const email = button.dataset.email;
        const role = button.dataset.role;
        const country = button.dataset.country;
        const cropLocation = button.dataset.crop_location;
        const address = button.dataset.address;

        editUserForm.action = `/admin/update_user/${id}`;
        document.getElementById('edit-name').value = name;
        document.getElementById('edit-email').value = email;
        document.getElementById('edit-role').value = role;
        document.getElementById('edit-country').value = country;
        document.getElementById('edit-crop_location').value = cropLocation;
        document.getElementById('edit-address').value = address;

        editUserOverlay.style.display = 'flex';
        setTimeout(() => editUserOverlay.classList.add('active'), 10);
    }
    
    window.closeEditUserModal = function() {
        editUserOverlay.classList.remove('active');
        setTimeout(() => {
            editUserOverlay.style.display = 'none';
        }, 200);
    }

    // Report Diagnosis Modal
    const reportOverlay = document.getElementById('report-diagnosis-overlay');
    const reportCancelBtn = document.getElementById('report-btn-cancel');
    const reportConfirmBtn = document.getElementById('report-btn-confirm');
    const reportReasonInput = document.getElementById('report-reason');
    let diagnosisToReportId = null;

    window.openReportModal = function(diagnosisId) {
        diagnosisToReportId = diagnosisId;
        reportReasonInput.value = ''; 
        reportOverlay.style.display = 'flex';
        setTimeout(() => reportOverlay.classList.add('active'), 10);
    }
    
    function closeReportModal() {
        reportOverlay.classList.remove('active');
        setTimeout(() => {
            reportOverlay.style.display = 'none';
            diagnosisToReportId = null;
        }, 200);
    }

    if (reportCancelBtn) {
        reportCancelBtn.addEventListener('click', closeReportModal);
    }

    if (reportConfirmBtn) {
        reportConfirmBtn.addEventListener('click', function() {
            const reason = reportReasonInput.value.trim();
            if (!reason) {
                showAlertModal('Error', 'Please provide a reason for your report.');
                return;
            }
            if (!diagnosisToReportId) return;

            reportConfirmBtn.textContent = 'Submitting...';
            reportConfirmBtn.disabled = true;

            fetch(`/api/report_diagnosis/${diagnosisToReportId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ reason: reason })
            })
            .then(response => response.json())
            .then(data => {
                closeReportModal();
                if (data.status === 'success') {
                    showAlertModal('Report Submitted', data.message);
                    const reportBtn = document.querySelector(`.btn-report-inaccuracy[data-diagnosis-id="${diagnosisToReportId}"]`);
                    const confirmBtn = document.querySelector(`.btn-confirm-accuracy[data-diagnosis-id="${diagnosisToReportId}"]`);
                    if (reportBtn) {
                        reportBtn.innerHTML = '<i class="fa-solid fa-flag"></i> Reported';
                        reportBtn.disabled = true;
                    }
                    if (confirmBtn) confirmBtn.disabled = true;

                } else {
                    showAlertModal('Error', data.message || 'Could not submit report.');
                }
            })
            .catch(error => {
                console.error('Error reporting diagnosis:', error);
                closeReportModal();
                showAlertModal('Error', 'An unexpected error occurred.');
            })
            .finally(() => {
                reportConfirmBtn.textContent = 'Submit Report';
                reportConfirmBtn.disabled = false;
            });
        });
    }

    // Accuracy/Report Button
    document.querySelectorAll('.btn-confirm-accuracy').forEach(button => {
        button.addEventListener('click', function() {
            const diagnosisId = this.dataset.diagnosisId;
            const originalText = this.innerHTML; 
            this.innerHTML = 'Submitting...';
            this.disabled = true;

            const reportBtn = this.closest('.log-actions, .suggestion-section').querySelector('.btn-report-inaccuracy');
            if (reportBtn) reportBtn.disabled = true;

            fetch(`/api/confirm_diagnosis/${diagnosisId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            })
            .then(response => response.json())
            .then(data => {
                if (data.status === 'success') {
                    showAlertModal('Feedback Received', data.message);
                    this.innerHTML = '<i class="fa-solid fa-check"></i> Confirmed!';
                } else {
                    showAlertModal('Error', data.message);
                    this.innerHTML = originalText;
                    this.disabled = false;
                    if (reportBtn) reportBtn.disabled = false; 
                }
            })
            .catch(error => {
                showAlertModal('Error', 'An unexpected error occurred.');
                this.innerHTML = originalText;
                this.disabled = false;
                if (reportBtn) reportBtn.disabled = false; 
            });
        });
    });

    document.querySelectorAll('.btn-report-inaccuracy').forEach(button => {
        button.addEventListener('click', function() {
            const diagnosisId = this.dataset.diagnosisId;
            window.openReportModal(diagnosisId);
        });
    });


    // Admin Charts
    const pieChartCtx = document.getElementById('feedbackPieChart');
    const barChartCtx = document.getElementById('inaccuracyBarChart');

    // Only run this code if we are on a page with the charts
    if (pieChartCtx || barChartCtx) {
        fetch('/api/admin/chart_data')
            .then(response => response.json())
            .then(data => {
                
                // Build Pie Chart
                if (pieChartCtx && data.pieData && (data.pieData.counts[0] > 0 || data.pieData.counts[1] > 0)) {
                    new Chart(pieChartCtx, {
                        type: 'doughnut',
                        data: {
                            labels: data.pieData.labels,
                            datasets: [{
                                data: data.pieData.counts,
                                backgroundColor: [
                                    'rgba(76, 175, 80, 0.7)',  
                                    'rgba(220, 53, 69, 0.7)'  
                                ],
                                borderColor: [
                                    '#4CAF50',
                                    '#dc3545'
                                ],
                                borderWidth: 1
                            }]
                        },
                        options: {
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: {
                                legend: { position: 'bottom' }
                            }
                        }
                    });
                } else if (pieChartCtx) {
                    // Show a message if no data
                    pieChartCtx.parentElement.innerHTML = '<p class="empty-state" style="padding-top: 50px;">No feedback data to display.</p>';
                }

                // Build Bar Chart
                if (barChartCtx && data.barData && data.barData.labels.length > 0) {
                    new Chart(barChartCtx, {
                        type: 'bar',
                        data: {
                            labels: data.barData.labels,
                            datasets: [{
                                label: 'Inaccuracy Reports',
                                data: data.barData.counts,
                                backgroundColor: 'rgba(248, 215, 218, 0.7)',
                                borderColor: 'rgba(220, 53, 69, 1)',  
                                borderWidth: 1
                            }]
                        },
                        options: {
                            indexAxis: 'y', // Makes it a horizontal 
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: { 
                                legend: { display: false },
                                title: { display: false }
                            },
                            scales: {
                                x: {
                                    beginAtZero: true,
                                    ticks: {
                                        stepSize: 1 // Only show whole numbers
                                    }
                                }
                            }
                        }
                    });
                } else if (barChartCtx) {
                    // Show a message if no data
                    barChartCtx.parentElement.innerHTML = '<p class="empty-state" style="padding-top: 50px;">No inaccuracy reports to display.</p>';
                }
            })
            .catch(error => console.error('Error fetching chart data:', error));
    }


}); 
