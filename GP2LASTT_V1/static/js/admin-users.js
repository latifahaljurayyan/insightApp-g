

const ROWS_PER_PAGE = 5;
let users         = [];
let filtered      = [];
let currentPage   = 1;
let editingIndex  = null;
let deletingIndex = null;

// ── Load users from Backend on page load ──
document.addEventListener('DOMContentLoaded', async function () {
  try {
    const res = await fetch('/api/admin/users');
    if (!res.ok) throw new Error('Failed to load users');
    users = await res.json();
    renderStats();
    filterUsers();
  } catch (err) {
    console.error(err);
    showToast('❌ Could not load users');
  }
});

// ── Stats 
function renderStats() {
  document.getElementById('totalUsers').textContent    = users.length;
  document.getElementById('activeUsers').textContent   = users.filter(function(u) { return u.status === 'active'; }).length;
  document.getElementById('inactiveUsers').textContent = users.filter(function(u) { return u.status === 'inactive'; }).length;
}

// ── Filter & Search 
function filterUsers() {
  const query  = document.getElementById('searchInput').value.trim().toLowerCase();
  const status = document.getElementById('statusFilter').value;

  filtered = users.filter(function(u) {
    const matchName   = u.name.toLowerCase().includes(query);
    const matchEmail  = u.email.toLowerCase().includes(query);
    const matchStatus = status === 'all' || u.status === status;
    return (matchName || matchEmail) && matchStatus;
  });

  currentPage = 1;
  renderTable();
  renderPagination();
}


function renderTable() {
  const tbody = document.getElementById('userTableBody');
  const start = (currentPage - 1) * ROWS_PER_PAGE;
  const page  = filtered.slice(start, start + ROWS_PER_PAGE);

  if (page.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; padding: 30px; color: #c4b5fd;">No users found.</td></tr>';
    return;
  }

  tbody.innerHTML = page.map(function(u) {
    const realIndex = users.indexOf(u);
    const label     = u.status.charAt(0).toUpperCase() + u.status.slice(1);
    return `
      <tr>
        <td>${u.name}</td>
        <td>${u.email}</td>
        <td><span class="status-badge ${u.status}">${label}</span></td>
        <td>
          <div class="action-btns">
            <button class="btn-edit"   onclick="openEditModal(${realIndex})">Edit</button>
            <button class="btn-delete" onclick="openDeleteModal(${realIndex})">Delete</button>
          </div>
        </td>
      </tr>
    `;
  }).join('');
}


function renderPagination() {
  const pagination = document.getElementById('pagination');
  const totalPages = Math.ceil(filtered.length / ROWS_PER_PAGE);

  if (totalPages <= 1) {
    pagination.innerHTML = '';
    return;
  }

  let html = '';
  for (let i = 1; i <= totalPages; i++) {
    const active = i === currentPage ? ' active' : '';
    html += `<button class="page-btn${active}" onclick="goToPage(${i})">${i}</button>`;
  }
  pagination.innerHTML = html;
}

function goToPage(page) {
  currentPage = page;
  renderTable();
  renderPagination();
}


function openModal(id) {
  document.getElementById(id).classList.add('show');
}

function closeModal(id) {
  document.getElementById(id).classList.remove('show');
}

// ── Edit 
function openEditModal(index) {
  editingIndex = index;
  const u = users[index];

  document.getElementById('editName').value   = u.name;
  document.getElementById('editEmail').value  = u.email;
  document.getElementById('editStatus').value = u.status;

 
  document.getElementById('editName').readOnly  = false;
  document.getElementById('editEmail').readOnly = false;
  document.getElementById('editName').style.opacity  = '1';
  document.getElementById('editEmail').style.opacity = '1';

  openModal('editModal');
}

// PUT / updates name, email and status
async function saveEdit() {
  if (editingIndex === null) return;

  const name   = document.getElementById('editName').value.trim();
  const email  = document.getElementById('editEmail').value.trim();
  const status = document.getElementById('editStatus').value;
  const userId = users[editingIndex].id;

  if (!name || !email) {
    showToast('⚠️ Please fill in all fields');
    return;
  }

  try {
    const res = await fetch(`/api/admin/users/${userId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email, status })
    });

    if (!res.ok) throw new Error('Failed to update user');

    
    users[editingIndex].name   = name;
    users[editingIndex].email  = email;
    users[editingIndex].status = status;

    closeModal('editModal');
    editingIndex = null;
    renderStats();
    filterUsers();
    showToast('✅ User updated successfully');
  } catch (err) {
    console.error(err);
    showToast('❌ An error occurred while updating');
  }
}

// ── Delete
function openDeleteModal(index) {
  deletingIndex = index;
  openModal('deleteModal');
}


async function confirmDelete() {
  if (deletingIndex === null) return;

  const userId = users[deletingIndex].id;

  try {
    const res = await fetch(`/api/admin/users/${userId}`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' }
    });

    if (!res.ok) throw new Error('Failed to delete user');

    users.splice(deletingIndex, 1);
    closeModal('deleteModal');
    deletingIndex = null;
    renderStats();
    filterUsers();
    showToast('🗑️ User deleted successfully');
  } catch (err) {
    console.error(err);
    showToast('❌ An error occurred while deleting');
  }
}


function showToast(msg) {
  const toast = document.getElementById('toast');
  toast.textContent = msg;
  toast.classList.add('show');
  setTimeout(function() {
    toast.classList.remove('show');
  }, 3000);
}


document.querySelectorAll('.modal-overlay').forEach(function(overlay) {
  overlay.addEventListener('click', function(e) {
    if (e.target === overlay) {
      overlay.classList.remove('open');
    }
  });
});
