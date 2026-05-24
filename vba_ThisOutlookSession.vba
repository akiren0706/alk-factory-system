' ==============================================
' ThisOutlookSession に貼り付けるコード
' 新しいメールが届いたとき自動で添付ファイルを保存する
' ==============================================

Private Sub Application_NewMailEx(ByVal EntryIDCollection As String)
    Dim ns As NameSpace
    Set ns = Application.GetNamespace("MAPI")

    Dim ids() As String
    ids = Split(EntryIDCollection, ",")

    Dim i As Integer
    For i = 0 To UBound(ids)
        On Error Resume Next
        Dim mail As Object
        Set mail = ns.GetItemFromID(Trim(ids(i)))
        If Err.Number <> 0 Then
            Err.Clear
        ElseIf TypeName(mail) = "MailItem" Then
            If InStr(LCase(mail.SenderEmailAddress), "1c_alk@rfpgroup.ru") > 0 Then
                Call SaveAttachments(mail)
            End If
        End If
        On Error GoTo 0
    Next i
End Sub
