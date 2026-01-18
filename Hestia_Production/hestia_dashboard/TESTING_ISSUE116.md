# Testing Guide - Issue #116 Login MVP

This document provides step-by-step instructions to test the Login MVP implementation.

## Prerequisites

- Dev server running: `npm run dev`
- Browser with DevTools (recommended: Chrome/Edge)

---

## Test 1: Mock Mode Login

**Setup:** Set `VITE_USE_MOCKS=true` in `.env`

1. **Navigate to login page:**
   - Open http://localhost:5173/login
   - ✅ Should see "Modo: DEMO" badge
   - ✅ Should see role selector dropdown

2. **Login as SUPERVISOR:**
   - Select "Supervisor" from dropdown
   - Click "Entrar como Demo"
   - ✅ Should navigate to `/tickets`
   - ✅ Topbar should show "Usuario SUPERVISOR"
   - ✅ Sidebar should show supervisor-specific options

3. **Test different roles:**
   - Logout (click × in topbar)
   - Repeat login with: RECEPCION, TECNICO, GERENTE
   - ✅ Verify Sidebar changes based on role (check permissions.ts)

**DevTools Check:**
- Open Application tab → Local Storage
- ✅ Key `hestia.auth.user` should exist
- ✅ Value should contain: `{name, email, role, is_superadmin}`

---

## Test 2: Protected Route Guard

**Setup:** Continue with mock mode

1. **Without login:**
   - Clear localStorage (Application → Storage → Clear site data)
   - Try to access http://localhost:5173/tickets
   - ✅ Should redirect to `/login`

2. **After login:**
   - Login as any role
   - ✅ Should access `/tickets` successfully
   - Navigate to `/tickets/1`
   - ✅ Should load ticket detail page

3. **Invalid routes:**
   - Try http://localhost:5173/invalid-route
   - ✅ Should redirect to `/` then `/login` (if not authenticated)

---

## Test 3: Logout Functionality

**Setup:** Login first

1. **Logout from dashboard:**
   - Click × button next to username in topbar
   - ✅ Should redirect to `/login`

2. **Verify session cleared:**
   - Check localStorage in DevTools
   - ✅ Key `hestia.auth.user` should be removed

3. **Verify cannot access protected routes:**
   - Try navigating to `/tickets`
   - ✅ Should redirect to `/login`

---

## Test 4: Session Persistence (Refresh)

**Setup:** Login first

1. **Login and refresh:**
   - Login as TECNICO
   - Press F5 / Ctrl+R to refresh page
   - ✅ Should remain at `/tickets`
   - ✅ Should still show "Usuario TECNICO"
   - ✅ Sidebar should maintain TECNICO permissions

2. **localStorage check:**
   - Open DevTools → Application → Local Storage
   - ✅ Key `hestia.auth.user` should persist
   - Modify the `role` value manually to "GERENTE"
   - Refresh page
   - ✅ Should now show GERENTE role and permissions

3. **Cross-tab persistence:**
   - Login in tab 1
   - Open new tab → Navigate to `/tickets`
   - ✅ Should be authenticated (shared localStorage)

---

## Test 5: Real Mode Login (Backend Required)

**Setup:** Set `VITE_USE_MOCKS=false` in `.env`

**Prerequisites:** Flask backend running with `/auth/login` endpoint

1. **Navigate to login:**
   - Open http://localhost:5173/login
   - ✅ Should see "Modo: PRODUCCIÓN" badge
   - ✅ Should see Email and Password fields

2. **Login with valid credentials:**
   - Enter valid email/password from backend
   - Click "Ingresar"
   - ✅ Should show "Ingresando..." loading state
   - **DevTools Network Tab:**
     - Check POST request to `/auth/login`
     - ✅ Should include `credentials: 'include'`
     - ✅ Should set session cookie
   - ✅ Should navigate to `/tickets` on success

3. **Login with invalid credentials:**
   - Enter wrong password
   - Click "Ingresar"
   - ✅ Should show error message (red box)
   - ✅ Should stay at `/login`

4. **Real logout:**
   - After successful login, click logout
   - **DevTools Network Tab:**
     - Check GET request to `/auth/logout`
   - ✅ Should clear localStorage
   - ✅ Should redirect to `/login`

---

## Test 6: Error Handling

**Setup:** Mock mode

1. **Network error simulation:**
   - Open DevTools → Network tab
   - Set throttling to "Offline"
   - Try to login
   - ✅ Should show error toast (if implemented)

2. **401 Auto-redirect:**
   - While logged in, manually delete session cookie (if testing real mode)
   - Navigate to a protected page
   - ✅ Should redirect to `/login` after 2s

---

## Expected Behavior Summary

| Scenario | Expected Result |
|----------|----------------|
| Access /tickets without login | Redirect to /login |
| Login with mock mode | Set user in localStorage, navigate to /tickets |
| Logout | Clear localStorage, navigate to /login |
| Refresh after login | Restore session from localStorage |
| Switch roles in mock | Sidebar updates with role permissions |
| Real mode login success | API call, cookie set, navigate to /tickets |
| Real mode login failure | Show error, stay at /login |

---

## Troubleshooting

**Issue:** Session not persisting after refresh
- Check DevTools console for errors
- Verify localStorage key: `hestia.auth.user`
- Ensure AuthProvider wraps all routes

**Issue:** Protected routes not redirecting
- Verify ProtectedRoute receives `isAuthenticated` prop
- Check AuthContext is providing correct state

**Issue:** Real mode login failing
- Verify Vite proxy config in `vite.config.ts`
- Check backend `/auth/login` endpoint accepts form-urlencoded
- Verify CORS and credentials settings

---

## Definition of Done Checklist

- ✅ Without login, cannot access `/tickets` (redirects to `/login`)
- ✅ Logout clears session and redirects to `/login`
- ✅ Mock mode allows role selection and changes Sidebar items
- ✅ Session persists across page refresh via localStorage
- ✅ Real mode calls POST `/auth/login` with credentials
- ✅ No new npm dependencies added
