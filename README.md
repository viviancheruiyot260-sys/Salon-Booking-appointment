# Glow & Grace Salon, Spa & Nail Studio

A small appointment-booking website for a salon, spa and nail studio. Customers read prices, pick a time and get an answer straight away: a free time is confirmed on the spot, and a taken time comes back with the nearest open times to pick from. The studio owner manages bookings in Django’s admin.

Nothing on the public site takes payment.

## What you need

- Python 3.12 or newer (the project was built with Python 3.12)
- `pip`
- A terminal

SQLite is included with Python and is used when `DATABASE_URL` is not set. PostgreSQL is optional and is described under production setup.

Fonts and Bootstrap are loaded from the internet when you open the site. The pages still work if those files are blocked; they just look plainer. Core booking does not depend on them.

## Run it on Ubuntu or another Linux machine

Ubuntu’s default Python does not always include the virtual-environment tool. Install it once:

```bash
sudo apt update
sudo apt install python3-venv python3-pip
```

From this folder (`glow_grace`):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py load_sample_services
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000/

The admin is at http://127.0.0.1:8000/admin/

`createsuperuser` asks you for a username, email and password. Those are not stored in the code. Use a password you can remember; Django will not accept a very common one.

`load_sample_services` can be run again. It adds any missing sample service and leaves rows that are already there, including prices you edited.

## Windows and macOS

Create and activate the virtual environment, then use the same `pip` and `manage.py` commands.

Windows (Command Prompt):

```bat
python -m venv .venv
.venv\Scripts\activate
```

Windows (PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## Try a booking

1. On the homepage, choose Hair, Spa & Wellness, or Nails, or open a service.
2. Choose **Book this service**. The form opens with that service selected.
3. Enter a name, a Kenyan mobile number such as `0712 345 678`, a future date, and a time inside the sample opening hours.
4. Press **Book appointment**. If the time is free you land on "Your appointment is confirmed." with a reference such as `GG-20261030-AB3K`.
5. Book the same service and time again with a different name and phone. The form comes back with "That time is already booked" and up to four open times. Tap one to book it.
6. **Send booking details on WhatsApp** is optional. You still have to press Send in WhatsApp, and the booking stands either way.

Sample opening hours, in Africa/Nairobi:

- Monday to Friday, 8:00 AM – 7:00 PM
- Saturday, 8:00 AM – 6:00 PM
- Sunday, 10:00 AM – 4:00 PM

The service must also finish before closing. A three-hour braid cannot start at 3:30 PM on a Sunday.

## Where the fictional details live

| What | Where to change it |
| --- | --- |
| Studio name, address, about text, displayed hours | `SALON` in `config/settings.py` |
| Prices, descriptions, durations, hiding a service | Django admin, or the database |
| Sample catalogue the first time | `salon/management/commands/load_sample_services.py` |
| WhatsApp number | `OWNER_WHATSAPP_NUMBER` in `.env` |
| Owner email notifications | `OWNER_EMAIL` and the `EMAIL_*` variables |
| Public email and Instagram links | `PUBLIC_CONTACT_EMAIL`, `SOCIAL_INSTAGRAM_URL` |

The homepage headline and the sentence under it are part of this demo and live in `salon/templates/salon/home.html`.

`254700000000` is a placeholder, not a real studio line. The site says so. Replace it before anyone treats the project as a real business. Leave `PUBLIC_CONTACT_EMAIL` and `SOCIAL_INSTAGRAM_URL` empty to hide those links.

Displayed hours in `SALON` are the words customers read. The times the form accepts are enforced in `salon/scheduling.py` (`WEEKDAY_HOURS`). Change both if the real hours differ.

## Change a price

1. Sign in at `/admin/`.
2. Open **Services**.
3. Edit the price in the list, or open the service.
4. Save.

New bookings copy the price at the moment they are made. Older bookings keep the price they were quoted. The browser cannot submit a different price; the server reads it from the service row.

To hide a service from the catalogue, turn off **Active**. Existing requests stay attached to it.

## WhatsApp

`OWNER_WHATSAPP_NUMBER` is the number the customer’s draft is addressed to. You can enter `0712345678` or `254712345678`.

After a request is saved, the success page builds a `https://wa.me/` link. The customer reviews the text and presses Send in WhatsApp. This project does not call the WhatsApp API, and clicking the button does not mean the studio received anything.

The saved request does not depend on that click.

## Email

Copy `.env.example` to `.env`.

For local development, keep:

```text
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
```

The message is printed in the terminal running `runserver`. It is not delivered to a real inbox. The success page says that.

Two emails go out for every confirmed booking:

- **Customer confirmation**, when the customer typed an email address. It has the reference, service, date, time, price, address and how to change or cancel, in plain text and a pink HTML layout (`salon/templates/salon/emails/`). Replies go to `OWNER_EMAIL`.
- **Owner copy**, when `OWNER_EMAIL` is set.

To deliver them for real, use SMTP. With Gmail, turn on 2-Step Verification, create an App Password at https://myaccount.google.com/apppasswords, then:

```text
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=yourstudio@gmail.com
EMAIL_HOST_PASSWORD=the-16-character-app-password
EMAIL_USE_TLS=true
DEFAULT_FROM_EMAIL=Glow & Grace <yourstudio@gmail.com>
OWNER_EMAIL=yourstudio@gmail.com
```

Restart `runserver` after editing `.env`. Any other SMTP provider works the same way with its own host, port and login.

If the mail server fails, the booking stays saved and the customer is told the email could not be sent, without the server error or the password. A repeated submit of the same booking does not send a second copy.

Do not put real passwords in templates, JavaScript, or git.

## How availability works

- Each category (Hair, Spa & Wellness, Nails) takes one appointment at a time. A manicure does not block a haircut at the same hour, but two hair appointments cannot overlap.
- Pending and Confirmed bookings occupy their time. Cancelled and Completed ones do not, so cancelling in the admin frees the slot.
- Online bookings are saved as **Confirmed** when the time is free. If the studio cannot honour one, set it to Cancelled in the admin and contact the customer.
- When a time is taken, the form suggests up to three open times on the same day (closest first), then the earliest open times over the next week.
- The free-time check and the save run in one transaction, so two customers pressing Book at the same moment cannot both get the same time.

The rule lives in `salon/availability.py` if the studio has more chairs or staff per category.

## Manage bookings

The admin is only for staff users created with `createsuperuser` (or another staff account you create there).

An owner can:

- search by reference, customer name, phone or email
- filter by status, date, category and service
- change status from the list: Pending, Confirmed, Cancelled, Completed
- use the actions to confirm, cancel or mark completed
- edit services

Customers cannot open `/admin/` and there is no public page that lists other people’s requests. The success page shows details only in the browser session that submitted the form.

There is no separate custom dashboard.

A repeated submit of the same name, phone, service, date and time within three minutes does not create a second row. A different customer asking for a taken time is shown open times instead, without seeing who has the slot.

## Tests

With the virtual environment active:

```bash
python manage.py test salon
```

## Production notes

Production is a different mode. In `.env`:

```text
DJANGO_ENV=production
DJANGO_SECRET_KEY=a-long-random-string-at-least-32-characters
DJANGO_ALLOWED_HOSTS=your-domain.example
DJANGO_CSRF_TRUSTED_ORIGINS=https://your-domain.example
DATABASE_URL=postgres://USER:PASSWORD@localhost:5432/glow_grace
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
```

`DJANGO_ENV=production` turns debug mode off, even if `DJANGO_DEBUG` is still true. It also requires the secret and the allowed hosts. Put the site behind HTTPS. `DJANGO_SECURE_SSL_REDIRECT` defaults to true in that mode. If a proxy terminates TLS, it should send `X-Forwarded-Proto: https`, or set `DJANGO_SECURE_SSL_REDIRECT=false` only when you understand the result.

Install the Postgres driver in the server environment:

```bash
pip install "psycopg[binary]>=3.2,<4"
```

Then:

```bash
python manage.py migrate
python manage.py load_sample_services
python manage.py collectstatic
python manage.py createsuperuser
```

`collectstatic` copies files into `staticfiles/`. Serve that directory and `media/` (uploaded service images) from the web server. A typical process launch, after `pip install gunicorn`, is:

```bash
gunicorn config.wsgi:application
```

Gunicorn is not required for local development and is not listed in `requirements.txt`.

Uploaded images use `media/`. Include that directory in backups together with the database.

## What needs something outside this project

| Feature | Needs |
| --- | --- |
| Local website and admin | Python, the requirements file, and a superuser |
| Real WhatsApp delivery | The customer’s own WhatsApp, and a real `OWNER_WHATSAPP_NUMBER` |
| Real email | SMTP host, mailbox, and `OWNER_EMAIL` |
| PostgreSQL | A database and `psycopg` |
| Public email or Instagram links | `PUBLIC_CONTACT_EMAIL` or `SOCIAL_INSTAGRAM_URL` |
| HTTPS and a public hostname | Your server, domain, and production env vars |

## Layout

```text
glow_grace/
├── manage.py
├── config/            settings, urls, wsgi
├── salon/             models, booking form, admin, templates, tests
├── static/            css, javascript, illustrations
├── requirements.txt
├── .env.example
└── README.md
```

Customer notes are stored as plain text and escaped when shown. Passwords and SMTP secrets stay in the environment, not in the templates.
