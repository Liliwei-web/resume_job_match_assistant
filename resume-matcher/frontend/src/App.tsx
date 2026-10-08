import { useEffect, useState, type ReactNode } from 'react'
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { api } from './api'
import type { User } from './types'
import Login from './pages/Login'
import Workspace from './pages/Workspace'
import ResumeWorkbench from './pages/ResumeWorkbench'
import History from './pages/History'
import AnalysisDetail from './pages/AnalysisDetail'

function Layout({
  user,
  onLogout,
  children,
}: {
  user: User
  onLogout: () => void
  children: ReactNode
}) {
  // 简历工作台是从「工作台」进去的子页面（/resumes/:id），
  // 分析回放页是从「历史记录」进去的子页面（/analyses/:id），都要算作父项的激活状态。
  const { pathname } = useLocation()
  const linkClass = (active: boolean) => (active ? 'nav-link active' : 'nav-link')
  const inResumePage = pathname.startsWith('/resumes/')

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true" />
          简历与岗位匹配助手
        </div>
        <nav>
          <Link to="/" className={linkClass(pathname === '/' || inResumePage)}>
            工作台
          </Link>
          {/* 简历详情页的返回入口放在导览区，页头就不再挂一个重复的「返回工作台」按钮。 */}
          {inResumePage && (
            <Link to="/" className="nav-sub">
              ← 返回工作台
            </Link>
          )}
          <Link
            to="/history"
            className={linkClass(
              pathname.startsWith('/history') || pathname.startsWith('/analyses/'),
            )}
          >
            历史记录
          </Link>
        </nav>
        <div className="sidebar-foot">
          <div className="who">
            {user.display_name}
            <span className="who-id">{user.username}</span>
          </div>
          <button onClick={onLogout}>退出登录</button>
        </div>
      </aside>
      <main className="page">{children}</main>
    </div>
  )
}

export default function App() {
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api
      .get<User>('/api/auth/me')
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
  }, [])

  async function logout() {
    try {
      await api.post('/api/auth/logout')
    } catch {
      /* ignore */
    }
    setUser(null)
  }

  if (loading) {
    return <div className="page-loading">正在加载…</div>
  }

  if (!user) {
    return (
      <BrowserRouter>
        <Routes>
          <Route path="*" element={<Login onLoggedIn={setUser} />} />
        </Routes>
      </BrowserRouter>
    )
  }

  return (
    <BrowserRouter>
      <Layout user={user} onLogout={logout}>
        <Routes>
          <Route path="/" element={<Workspace />} />
          <Route path="/resumes/:resumeId" element={<ResumeWorkbench />} />
          <Route path="/history" element={<History />} />
          <Route path="/analyses/:analysisId" element={<AnalysisDetail />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  )
}
