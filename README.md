<div align="center">
  <h1>Alphax ESS</h1>
  <p>Employee Self Service for ERPNext</p>
  
  [![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
  [![Frappe](https://img.shields.io/badge/Frappe-Framework-orange.svg)](https://frappeframework.com)
</div>

---

## What is this?

This is the backend component for Alphax ESS - a mobile app that brings ERPNext to your phone. Employees can manage their HR tasks, sales activities, and projects right from their mobile devices.

---

## Features

**HR & Attendance**
- Apply for leaves and track approvals
- Check-in/check-out with geo-fencing
- Offline attendance support
- View salary slips and attendance history
- Submit expense claims

**Sales & CRM**
- Create sales orders and quotations
- Manage customer visits
- Track sales activities

**Tasks & Projects**
- Assign and manage tasks
- Track project progress
- Approve workflows on the go

**Other Features**
- Real-time push notifications
- Multilingual support
- Biometric authentication
- Posts, polls, and team updates

---

## Installation

You need ERPNext and HRMS installed on your server. Then:

**1. Get the app**

```bash
# Get the app
bench get-app employee_self_service
```

**2. Install on your site**

```bash
bench --site [your-site-name] install-app employee_self_service
bench --site [your-site-name] migrate
bench restart
```

**3. Configure**

Go to **Setup > Employee Self Service Settings** in your ERPNext desk and configure permissions and notifications.

**4. Connect mobile app**

Download the mobile app and login with your ERPNext credentials. That's it!

---

## Version Compatibility

| Branch | Frappe/ERPNext Version |
|--------|----------------------|
| version-13 | 13.x |
| version-14 | 14.x |
| version-15 | 15.x |
| version-16 | 16.x (latest) |

---

## License

Open source under GPL v3.0 - use it freely, modify it, share it.

---

## About

Built with ❤️ by Alphax using the Frappe Framework.
