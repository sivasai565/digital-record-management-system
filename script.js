document.addEventListener('DOMContentLoaded', function () {
    const toggleButtons = document.querySelectorAll('.password-toggle');
    toggleButtons.forEach(function (button) {
        button.addEventListener('click', function () {
            const targetId = button.getAttribute('data-target');
            const input = document.getElementById(targetId);
            if (!input) return;
            const isPassword = input.type === 'password';
            input.type = isPassword ? 'text' : 'password';
            button.textContent = isPassword ? '🙈' : '👁';
        });
    });

    const materialForm = document.getElementById('material-form');
    if (materialForm) {
        const totalInput = document.getElementById('total_stock');
        const usageInput = document.getElementById('today_usage');
        const remainingField = document.getElementById('remaining_stock_value');

        function updateRemainingStock() {
            const total = parseFloat(totalInput.value || 0);
            const usage = parseFloat(usageInput.value || 0);
            const remaining = Math.max(total - usage, 0);
            if (remainingField) {
                remainingField.value = remaining.toFixed(2);
            }
        }

        totalInput.addEventListener('input', updateRemainingStock);
        usageInput.addEventListener('input', updateRemainingStock);

        materialForm.addEventListener('submit', function (event) {
            const total = parseFloat(totalInput.value || 0);
            const usage = parseFloat(usageInput.value || 0);
            if (usage > total) {
                event.preventDefault();
                alert("Today's usage cannot be greater than total stock.");
            }
        });
    }

    const paymentForm = document.getElementById('payment-form');
    if (paymentForm) {
        const totalInput = document.getElementById('total_amount');
        const paidInput = document.getElementById('paid_amount');
        const remainingField = document.getElementById('remaining_amount_value');
        const statusField = document.getElementById('payment_status_value');

        function updatePaymentFields() {
            const total = parseFloat(totalInput.value || 0);
            const paid = parseFloat(paidInput.value || 0);
            const remaining = total - paid;
            if (remainingField) {
                remainingField.value = remaining.toFixed(2);
            }
            if (statusField) {
                let status = 'PENDING';
                if (Math.abs(remaining) < 0.0001) {
                    status = 'PAID';
                } else if (paid > 0 && remaining > 0) {
                    status = 'PARTIAL';
                }
                statusField.value = status;
            }
        }

        totalInput.addEventListener('input', updatePaymentFields);
        paidInput.addEventListener('input', updatePaymentFields);

        paymentForm.addEventListener('submit', function (event) {
            const total = parseFloat(totalInput.value || 0);
            const paid = parseFloat(paidInput.value || 0);
            if (paid > total) {
                event.preventDefault();
                alert('Paid amount cannot be greater than total amount.');
            }
        });
    }

    const materialToggle = document.getElementById('toggle-material-form');
    if (materialToggle) {
        const panel = document.getElementById('material-form-panel');
        materialToggle.addEventListener('click', function () {
            if (panel) {
                panel.classList.toggle('hidden');
            }
        });
    }

    const paymentSearch = document.getElementById('payment-search');
    if (paymentSearch) {
        paymentSearch.addEventListener('input', function () {
            const searchText = paymentSearch.value.trim().toLowerCase();
            const rows = document.querySelectorAll('#payment-table-body tr');
            rows.forEach(function (row) {
                const supplier = row.getAttribute('data-supplier') || '';
                const invoice = row.getAttribute('data-invoice') || '';
                const matches = supplier.includes(searchText) || invoice.includes(searchText);
                row.style.display = matches || !searchText ? '' : 'none';
            });
        });
    }

    const materialSearch = document.getElementById('material-search');
    if (materialSearch) {
        materialSearch.addEventListener('input', function () {
            const searchText = materialSearch.value.trim().toLowerCase();
            const rows = document.querySelectorAll('#material-table-body tr');
            rows.forEach(function (row) {
                const materialName = row.getAttribute('data-name') || '';
                const remarks = row.getAttribute('data-remarks') || '';
                const matches = materialName.includes(searchText) || remarks.includes(searchText);
                row.style.display = matches || !searchText ? '' : 'none';
            });
        });
    }

    const deleteButtons = document.querySelectorAll('[data-confirm-delete]');
    deleteButtons.forEach(function (button) {
        button.addEventListener('click', function (event) {
            const message = button.getAttribute('data-confirm-delete');
            const confirmed = window.confirm(message);
            if (!confirmed) {
                event.preventDefault();
                event.stopPropagation();
                return;
            }
        });
    });

    const registerForm = document.getElementById('register-form');
    if (registerForm) {
        registerForm.addEventListener('submit', function (event) {
            const password = document.getElementById('register-password');
            const confirmPassword = document.getElementById('confirm-password');
            if (password && confirmPassword && password.value !== confirmPassword.value) {
                event.preventDefault();
                alert('Passwords do not match');
            }
            if (password && !/[A-Za-z]/.test(password.value) || !/[0-9]/.test(password.value)) {
                event.preventDefault();
                alert('Password must contain alphabets and numbers.');
            }
        });
    }
});
