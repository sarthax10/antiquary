import { Navigate, Route, Routes } from "react-router-dom";
import { RequireAdmin, RequireApproved } from "./components/ProtectedRoute";
import AdminUsers from "./pages/AdminUsers";
import Archive from "./pages/Archive";
import Create from "./pages/Create";
import Library from "./pages/Library";
import Login from "./pages/Login";
import Pending from "./pages/Pending";
import Review from "./pages/Review";
import Signup from "./pages/Signup";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/pending" element={<Pending />} />

      <Route element={<RequireApproved />}>
        <Route path="/create" element={<Create />} />
        <Route path="/review" element={<Review />} />
        <Route path="/library" element={<Library />} />
        <Route path="/archive" element={<Archive />} />
      </Route>

      <Route element={<RequireAdmin />}>
        <Route path="/admin/users" element={<AdminUsers />} />
      </Route>

      <Route path="/" element={<Navigate to="/create" replace />} />
      <Route path="*" element={<Navigate to="/create" replace />} />
    </Routes>
  );
}
