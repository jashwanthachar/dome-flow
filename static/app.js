/**
 * CivicEye - Tumakuru Civic Grievance System
 * Frontend Client Script
 */

document.addEventListener("DOMContentLoaded", () => {
  console.log("CivicEye initialized for Tumakuru Civic Grievance System.");

  // Check health endpoint on initialization
  fetch("/health")
    .then(res => res.json())
    .then(data => {
      console.log("CivicEye backend connection:", data.status);
    })
    .catch(err => {
      console.warn("CivicEye backend notice:", err.message);
    });
});
