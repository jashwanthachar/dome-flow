/**
 * CivicEye - Tumakuru Civic Grievance System
 * Frontend Client Script
 */

document.addEventListener("DOMContentLoaded", () => {
  // Add subtle ripple / tactile touch effect on cards
  const cards = document.querySelectorAll(".action-card, .btn-quick-link");
  cards.forEach(card => {
    card.addEventListener("touchstart", () => {
      card.style.transform = "scale(0.985)";
    }, { passive: true });

    card.addEventListener("touchend", () => {
      card.style.transform = "";
    }, { passive: true });
  });
});
