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
import StoryDetail from "./pages/StoryDetail";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/pending" element={<Pending />} />

      {/* One layout route renders the app shell once for every signed-in page. */}
      <Route element={<RequireApproved />}>
        <Route path="/create" element={<Create />} />
        <Route path="/review" element={<Review />} />
        <Route path="/library" element={<Library />} />
        <Route path="/archive" element={<Archive />} />
        <Route path="/stories/:id" element={<StoryDetail />} />

        <Route element={<RequireAdmin />}>
          <Route path="/admin/users" element={<AdminUsers />} />
        </Route>
      </Route>

      <Route path="/" element={<Navigate to="/create" replace />} />
      <Route path="*" element={<Navigate to="/create" replace />} />
    </Routes>
  );
}
