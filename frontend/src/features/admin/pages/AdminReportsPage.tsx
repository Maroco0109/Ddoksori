import { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { apiClient } from '@/shared/api/client';
import type { Report, ReportSearchParams } from '@/shared/types/admin';
import { useAdminStore } from '../admin.store';
import { getMockData } from '../mockData';

export default function AdminReportsPage() {
  const [searchParams] = useSearchParams();
  const [reports, setReports] = useState<Report[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectedReport, setSelectedReport] = useState<Report | null>(null);
  const adminToken = useAdminStore((state) => state.adminToken);

  const [searchFilters, setSearchFilters] = useState<ReportSearchParams>({
    type: undefined,
    status: undefined,
    page: 1,
    limit: 20,
  });

  useEffect(() => {
    const statusParam = searchParams.get('status');
    if (statusParam) {
      setSearchFilters((prev) => ({ ...prev, status: statusParam as any }));
    }
  }, [searchParams]);

  useEffect(() => {
    fetchReports();
  }, [searchFilters]);

  const fetchReports = async () => {
    setIsLoading(true);
    try {
      // 테스트 모드인 경우 mock 데이터 사용
      if (adminToken === 'test-token-1234') {
        const data = getMockData('/api/admin/reports', searchFilters);
        setReports(data);
      } else {
        const data = await apiClient.get<Report[]>('/api/admin/reports', searchFilters);
        setReports(data);
      }
    } catch (error) {
      console.error('신고 목록 로딩 실패:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleUpdateReportStatus = async (
    reportId: number,
    newStatus: 'reviewed' | 'resolved' | 'rejected',
    adminNote?: string
  ) => {
    try {
      // 테스트 모드에서는 시뮬레이션만
      if (adminToken === 'test-token-1234') {
        alert('신고 처리 상태가 변경되었습니다. (테스트 모드)');
        fetchReports();
        setSelectedReport(null);
      } else {
        await apiClient.put(`/api/admin/reports/${reportId}/status`, {
          status: newStatus,
          adminNote,
        });
        alert('신고 처리 상태가 변경되었습니다.');
        fetchReports();
        setSelectedReport(null);
      }
    } catch (error) {
      alert('상태 변경에 실패했습니다.');
    }
  };

  const handleViewReportDetail = async (reportId: number) => {
    try {
      // 테스트 모드인 경우 mock 데이터 사용
      if (adminToken === 'test-token-1234') {
        const report = getMockData(`/api/admin/reports/${reportId}`);
        setSelectedReport(report);
      } else {
        const report = await apiClient.get<Report>(`/api/admin/reports/${reportId}`);
        setSelectedReport(report);
      }
    } catch (error) {
      alert('신고 내용을 불러올 수 없습니다.');
    }
  };

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">신고 관리</h1>

      {/* 검색 필터 */}
      <div className="bg-white p-4 rounded-lg shadow mb-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <select
            value={searchFilters.type || ''}
            onChange={(e) =>
              setSearchFilters({
                ...searchFilters,
                type: e.target.value === '' ? undefined : (e.target.value as any),
              })
            }
            className="px-3 py-2 border border-gray-300 rounded-md text-sm"
          >
            <option value="">전체 유형</option>
            <option value="post">게시글</option>
            <option value="comment">댓글</option>
          </select>

          <select
            value={searchFilters.status || ''}
            onChange={(e) =>
              setSearchFilters({
                ...searchFilters,
                status: e.target.value === '' ? undefined : (e.target.value as any),
              })
            }
            className="px-3 py-2 border border-gray-300 rounded-md text-sm"
          >
            <option value="">전체 상태</option>
            <option value="pending">대기</option>
            <option value="reviewed">검토 완료</option>
            <option value="resolved">처리 완료</option>
            <option value="rejected">기각</option>
          </select>

          <button
            onClick={fetchReports}
            className="px-4 py-2 bg-gray-800 text-white text-sm rounded-md hover:bg-gray-900"
          >
            검색
          </button>
        </div>
      </div>

      {/* 신고 목록 */}
      {isLoading ? (
        <div className="text-center py-12 text-gray-500">로딩 중...</div>
      ) : (
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase w-12">ID</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase w-16 whitespace-nowrap">유형</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase w-40">대상</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase w-20 whitespace-nowrap">신고자</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase w-48">신고 사유</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase w-24 whitespace-nowrap">신고일</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase w-20 whitespace-nowrap">상태</th>
                <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase w-20 whitespace-nowrap">작업</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {reports.map((report) => (
                <tr
                  key={report.id}
                  className={report.status === 'pending' ? 'bg-yellow-50' : ''}
                >
                  <td className="px-4 py-3 text-xs w-12">{report.id}</td>
                  <td className="px-4 py-3 text-xs w-16 whitespace-nowrap">
                    <span className="px-2 py-1 bg-gray-100 rounded text-xs whitespace-nowrap">
                      {report.type === 'post' ? '게시글' : '댓글'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs w-40">
                    <div className="truncate" title={report.targetTitle || report.targetContent}>
                      {report.targetTitle || report.targetContent}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-xs w-20 whitespace-nowrap">{report.reporterName}</td>
                  <td className="px-4 py-3 text-xs w-48">
                    <div className="truncate" title={report.reason}>
                      {report.reason}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-xs w-24 whitespace-nowrap">{new Date(report.createdAt).toLocaleDateString()}</td>
                  <td className="px-4 py-3 text-xs w-20 whitespace-nowrap">
                    <span
                      className={`px-2 py-1 rounded-full text-xs whitespace-nowrap ${
                        report.status === 'pending'
                          ? 'bg-yellow-100 text-yellow-800'
                          : report.status === 'reviewed'
                          ? 'bg-blue-100 text-blue-800'
                          : report.status === 'resolved'
                          ? 'bg-green-100 text-green-800'
                          : 'bg-gray-100 text-gray-800'
                      }`}
                    >
                      {report.status === 'pending'
                        ? '대기'
                        : report.status === 'reviewed'
                        ? '검토 완료'
                        : report.status === 'resolved'
                        ? '처리 완료'
                        : '기각'}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs w-20 whitespace-nowrap">
                    <button
                      onClick={() => handleViewReportDetail(report.id)}
                      className="text-blue-600 hover:underline text-xs whitespace-nowrap"
                    >
                      상세보기
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {reports.length === 0 && (
            <div className="text-center py-12 text-gray-500">신고 내역이 없습니다.</div>
          )}
        </div>
      )}

      {/* 신고 상세 모달 */}
      {selectedReport && (
        <ReportDetailModal
          report={selectedReport}
          onClose={() => setSelectedReport(null)}
          onUpdateStatus={handleUpdateReportStatus}
        />
      )}
    </div>
  );
}

interface ReportDetailModalProps {
  report: Report;
  onClose: () => void;
  onUpdateStatus: (reportId: number, newStatus: 'reviewed' | 'resolved' | 'rejected', adminNote?: string) => void;
}

function ReportDetailModal({ report, onClose, onUpdateStatus }: ReportDetailModalProps) {
  const [adminNote, setAdminNote] = useState(report.adminNote || '');
  const [selectedStatus, setSelectedStatus] = useState<'reviewed' | 'resolved' | 'rejected'>('reviewed');

  const handleSubmit = () => {
    onUpdateStatus(report.id, selectedStatus, adminNote);
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 max-w-3xl w-full max-h-[80vh] overflow-y-auto">
        <div className="flex justify-between items-start mb-6">
          <h2 className="text-2xl font-bold">신고 상세 정보</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-700">
            ✕
          </button>
        </div>

        <div className="space-y-6">
          {/* 신고 기본 정보 */}
          <div className="border-b pb-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700">신고 ID</label>
                <p className="mt-1 text-sm text-gray-900">{report.id}</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">신고 유형</label>
                <p className="mt-1 text-sm text-gray-900">
                  {report.type === 'post' ? '게시글' : '댓글'}
                </p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">신고자</label>
                <p className="mt-1 text-sm text-gray-900">{report.reporterName}</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700">신고일시</label>
                <p className="mt-1 text-sm text-gray-900">
                  {new Date(report.createdAt).toLocaleString()}
                </p>
              </div>
            </div>
          </div>

          {/* 대상 내용 */}
          <div className="border-b pb-4">
            <label className="block text-sm font-medium text-gray-700 mb-2">신고 대상 내용</label>
            {report.targetTitle && (
              <p className="font-semibold mb-2">{report.targetTitle}</p>
            )}
            <div className="bg-gray-50 p-4 rounded-lg">
              <p className="text-sm text-gray-900 whitespace-pre-wrap">{report.targetContent}</p>
            </div>
          </div>

          {/* 신고 사유 */}
          <div className="border-b pb-4">
            <label className="block text-sm font-medium text-gray-700 mb-2">신고 사유</label>
            <div className="bg-red-50 p-4 rounded-lg">
              <p className="text-sm text-gray-900">{report.reason}</p>
            </div>
          </div>

          {/* 현재 상태 */}
          <div className="border-b pb-4">
            <label className="block text-sm font-medium text-gray-700 mb-2">현재 처리 상태</label>
            <span
              className={`px-3 py-1 rounded-full text-sm ${
                report.status === 'pending'
                  ? 'bg-yellow-100 text-yellow-800'
                  : report.status === 'reviewed'
                  ? 'bg-blue-100 text-blue-800'
                  : report.status === 'resolved'
                  ? 'bg-green-100 text-green-800'
                  : 'bg-gray-100 text-gray-800'
              }`}
            >
              {report.status === 'pending'
                ? '대기 중'
                : report.status === 'reviewed'
                ? '검토 완료'
                : report.status === 'resolved'
                ? '처리 완료'
                : '기각됨'}
            </span>
          </div>

          {/* 처리 */}
          {report.status === 'pending' || report.status === 'reviewed' ? (
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">처리 상태 변경</label>
                <select
                  value={selectedStatus}
                  onChange={(e) => setSelectedStatus(e.target.value as any)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
                >
                  <option value="reviewed">검토 완료</option>
                  <option value="resolved">처리 완료</option>
                  <option value="rejected">기각</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">관리자 메모</label>
                <textarea
                  value={adminNote}
                  onChange={(e) => setAdminNote(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md h-24"
                  placeholder="처리 내용이나 사유를 입력하세요"
                />
              </div>

              <div className="flex gap-2 justify-end">
                <button
                  onClick={onClose}
                  className="px-4 py-2 border border-gray-300 rounded-md hover:bg-gray-50"
                >
                  취소
                </button>
                <button
                  onClick={handleSubmit}
                  className="px-4 py-2 bg-teal-600 text-white rounded-md hover:bg-teal-700"
                >
                  처리 완료
                </button>
              </div>
            </div>
          ) : (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">관리자 메모</label>
              <div className="bg-gray-50 p-4 rounded-lg">
                <p className="text-sm text-gray-900">
                  {report.adminNote || '메모가 없습니다.'}
                </p>
              </div>
              <div className="flex justify-end mt-4">
                <button
                  onClick={onClose}
                  className="px-4 py-2 bg-gray-800 text-white text-sm rounded-md hover:bg-gray-900"
                >
                  닫기
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
