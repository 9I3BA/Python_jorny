// Global utilities for PyLearn

// Auto-dismiss flash messages
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.flash').forEach(el => {
    setTimeout(() => {
      el.style.transition = 'opacity .5s';
      el.style.opacity = '0';
      setTimeout(() => el.remove(), 500);
    }, 4000);
  });

  // Activate nav user menu on mobile tap
  const userMenu = document.querySelector('.user-menu');
  if (userMenu) {
    userMenu.addEventListener('click', (e) => {
      const dd = userMenu.querySelector('.dropdown-menu');
      if (dd) dd.style.display = dd.style.display === 'block' ? 'none' : 'block';
    });
    document.addEventListener('click', (e) => {
      if (!userMenu.contains(e.target)) {
        const dd = userMenu.querySelector('.dropdown-menu');
        if (dd) dd.style.display = '';
      }
    });
  }
});
