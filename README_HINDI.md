
# Vishal Mart — E-commerce Starter (Flask + Render)

इस ZIP में customer shopping website और admin panel का शुरुआती working project है।

## इसमें क्या है
- Mobile-friendly product storefront, search, category filters और product detail pages
- Cart, checkout, Cash on Delivery और order recording
- Admin dashboard: total sales, today/week/month sales, order/customer/product counts, 7-day sales graph, low-stock alerts, best-selling products और recent orders
- Product add/edit/delete, sale price/MRP, category/subcategory, sizes/colors, stock
- Android Gallery से multiple image और video upload
- CSV bulk product import
- Order status management, customer list, store settings और `/health` endpoint

## Local run
1. Python 3.11 या 3.12 install करें।
2. Terminal में project folder खोलें।
3. `pip install -r requirements.txt`
4. `ADMIN_USERNAME=admin` और `ADMIN_PASSWORD` environment variables set करें। Local quick demo में fallback password `admin12345` है—live deployment पर इसे इस्तेमाल न करें।
5. `python app.py`
6. Browser में `http://127.0.0.1:5000` खोलें।
7. Admin: `/admin/login`

## Render deployment
1. ZIP extract करें।
2. सभी files GitHub repository की root में upload करें।
3. Render में New + Web Service चुनकर repository connect करें।
4. Build Command: `pip install -r requirements.txt`
5. Start Command: `gunicorn app:app`
6. Environment variables:
   - `ADMIN_USERNAME` = अपना admin username
   - `ADMIN_PASSWORD` = लंबा, unique password
   - `SECRET_KEY` = random secret
   - `DATABASE_URL` = managed PostgreSQL database का internal URL (recommended for production)
7. Deploy के बाद `/health` खोलकर `{"status":"ok"...}` देख सकते हैं।

## बहुत जरूरी production notes
- Render के सामान्य ephemeral filesystem पर SQLite और uploaded files स्थायी नहीं हैं। Real store के लिए PostgreSQL और persistent disk या Cloudinary/S3 जैसी image storage जोड़ें। इस starter में upload folder local filesystem पर है; बिना persistent storage deploy/restart पर uploaded photos गायब हो सकती हैं।
- `UPI` checkout विकल्प केवल payment preference रिकॉर्ड करता है; यह payment collect/verify नहीं करता। असली online payment के लिए Razorpay/Cashfree जैसे gateway का merchant setup, server-side verification और webhook चाहिए।
- यह starter COD checkout के orders बनाता है; shipping courier API, email/SMS OTP, customer authentication, refunds, taxes/GST invoices, supplier marketplace, referral wallet और advanced permissions अभी production-ready integrated नहीं हैं।
- Admin default credentials बदलना अनिवार्य है। Admin panel public internet पर खोलने से पहले HTTPS, strong secrets, backups, rate limiting, image scanning, privacy policy और security review जोड़ें।
- CSV import में image URL import नहीं होता; product edit page पर photos upload करें।
