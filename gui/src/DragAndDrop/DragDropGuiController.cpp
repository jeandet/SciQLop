#include "DragAndDrop/DragDropGuiController.h"
#include "DragAndDrop/DragDropScroller.h"
#include "DragAndDrop/DragDropTabSwitcher.h"
#include "SqpApplication.h"
#include "Visualization/VisualizationDragDropContainer.h"
#include "Visualization/VisualizationDragWidget.h"
#include "Visualization/VisualizationWidget.h"
#include "Visualization/operations/FindVariableOperation.h"

#include "DataSource/DataSourceController.h"
#include "Variable/VariableController2.h"

#include "Common/MimeTypesDef.h"
#include "Common/VisualizationDef.h"

#include <QDir>
#include <QLabel>
#include <QUrl>
#include <QVBoxLayout>


Q_LOGGING_CATEGORY(LOG_DragDropGuiController, "DragDropGuiController")


struct DragDropGuiController::DragDropGuiControllerPrivate
{

    VisualizationDragWidget* m_CurrentDragWidget = nullptr;
    std::unique_ptr<QWidget> m_PlaceHolder = nullptr;
    QLabel* m_PlaceHolderLabel;
    QWidget* m_PlaceBackground;
    std::unique_ptr<DragDropScroller> m_DragDropScroller = nullptr;
    std::unique_ptr<DragDropTabSwitcher> m_DragDropTabSwitcher = nullptr;
    QString m_ImageTempUrl; // Temporary file for image url generated by the drag & drop. Not using
                            // QTemporaryFile to have a name which is not generated.

    VisualizationDragWidget* m_HighlightedDragWidget = nullptr;

    QMetaObject::Connection m_DragWidgetDestroyedConnection;
    QMetaObject::Connection m_HighlightedWidgetDestroyedConnection;

    QList<QWidget*> m_WidgetToClose;

    explicit DragDropGuiControllerPrivate()
            : m_PlaceHolder { std::make_unique<QWidget>() }
            , m_DragDropScroller { std::make_unique<DragDropScroller>() }
            , m_DragDropTabSwitcher { std::make_unique<DragDropTabSwitcher>() }
    {

        auto layout = new QVBoxLayout { m_PlaceHolder.get() };
        layout->setSpacing(0);
        layout->setContentsMargins(0, 0, 0, 0);

        m_PlaceHolderLabel = new QLabel { "", m_PlaceHolder.get() };
        m_PlaceHolderLabel->setMinimumHeight(25);
        layout->addWidget(m_PlaceHolderLabel);

        m_PlaceBackground = new QWidget { m_PlaceHolder.get() };
        m_PlaceBackground->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
        layout->addWidget(m_PlaceBackground);

        sqpApp->installEventFilter(m_DragDropScroller.get());
        sqpApp->installEventFilter(m_DragDropTabSwitcher.get());

        m_ImageTempUrl = QDir::temp().absoluteFilePath("Sciqlop_graph.png");
    }

    void preparePlaceHolder(
        DragDropGuiController::PlaceHolderType type, const QString& topLabelText) const
    {
        if (m_CurrentDragWidget)
        {
            m_PlaceHolder->setMinimumSize(m_CurrentDragWidget->size());
            m_PlaceHolder->setSizePolicy(m_CurrentDragWidget->sizePolicy());
        }
        else
        {
            // Configuration of the placeHolder when there is no dragWidget
            // (for instance with a drag from a variable)

            m_PlaceHolder->setMinimumSize(0, GRAPH_MINIMUM_HEIGHT);
            m_PlaceHolder->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
        }

        switch (type)
        {
            case DragDropGuiController::PlaceHolderType::Graph:
                m_PlaceBackground->setStyleSheet(
                    "background-color: #BBD5EE; border: 1px solid #2A7FD4");
                break;
            case DragDropGuiController::PlaceHolderType::Zone:
            case DragDropGuiController::PlaceHolderType::Default:
                m_PlaceBackground->setStyleSheet(
                    "background-color: #BBD5EE; border: 2px solid #2A7FD4");
                m_PlaceHolderLabel->setStyleSheet("color: #2A7FD4");
                break;
        }

        m_PlaceHolderLabel->setText(topLabelText);
        m_PlaceHolderLabel->setVisible(!topLabelText.isEmpty());
    }
};


DragDropGuiController::DragDropGuiController()
        : impl { spimpl::make_unique_impl<DragDropGuiControllerPrivate>() }
{
}

DragDropGuiController::~DragDropGuiController()
{
    QFile::remove(impl->m_ImageTempUrl);
}

void DragDropGuiController::resetDragAndDrop()
{
    setCurrentDragWidget(nullptr);
    impl->m_HighlightedDragWidget = nullptr;
}

void DragDropGuiController::setCurrentDragWidget(VisualizationDragWidget* dragWidget)
{
    if (impl->m_CurrentDragWidget)
    {

        QObject::disconnect(impl->m_DragWidgetDestroyedConnection);
    }

    if (dragWidget)
    {
        // ensures the impl->m_CurrentDragWidget is reset when the widget is destroyed
        impl->m_DragWidgetDestroyedConnection = QObject::connect(dragWidget,
            &VisualizationDragWidget::destroyed, [this]() { impl->m_CurrentDragWidget = nullptr; });
    }

    impl->m_CurrentDragWidget = dragWidget;
}

VisualizationDragWidget* DragDropGuiController::getCurrentDragWidget() const
{
    return impl->m_CurrentDragWidget;
}

QWidget& DragDropGuiController::placeHolder() const
{
    return *impl->m_PlaceHolder;
}

void DragDropGuiController::insertPlaceHolder(
    QVBoxLayout* layout, int index, PlaceHolderType type, const QString& topLabelText)
{
    removePlaceHolder();
    impl->preparePlaceHolder(type, topLabelText);
    layout->insertWidget(index, impl->m_PlaceHolder.get());
    impl->m_PlaceHolder->show();
}

void DragDropGuiController::removePlaceHolder()
{
    auto parentWidget = impl->m_PlaceHolder->parentWidget();
    if (parentWidget)
    {
        parentWidget->layout()->removeWidget(impl->m_PlaceHolder.get());
        impl->m_PlaceHolder->setParent(nullptr);
        impl->m_PlaceHolder->hide();
    }
}

bool DragDropGuiController::isPlaceHolderSet() const
{
    return impl->m_PlaceHolder->parentWidget();
}

void DragDropGuiController::addDragDropScrollArea(QScrollArea* scrollArea)
{
    impl->m_DragDropScroller->addScrollArea(scrollArea);
}

void DragDropGuiController::removeDragDropScrollArea(QScrollArea* scrollArea)
{
    impl->m_DragDropScroller->removeScrollArea(scrollArea);
}

void DragDropGuiController::addDragDropTabBar(QTabBar* tabBar)
{
    impl->m_DragDropTabSwitcher->addTabBar(tabBar);
}

void DragDropGuiController::removeDragDropTabBar(QTabBar* tabBar)
{
    impl->m_DragDropTabSwitcher->removeTabBar(tabBar);
}

QUrl DragDropGuiController::imageTemporaryUrl(const QImage& image) const
{
    image.save(impl->m_ImageTempUrl);
    return QUrl::fromLocalFile(impl->m_ImageTempUrl);
}

void DragDropGuiController::setHightlightedDragWidget(VisualizationDragWidget* dragWidget)
{
    if (impl->m_HighlightedDragWidget)
    {
        impl->m_HighlightedDragWidget->highlightForMerge(false);
        QObject::disconnect(impl->m_HighlightedWidgetDestroyedConnection);
    }

    if (dragWidget)
    {
        dragWidget->highlightForMerge(true);

        // ensures the impl->m_HighlightedDragWidget is reset when the widget is destroyed
        impl->m_DragWidgetDestroyedConnection
            = QObject::connect(dragWidget, &VisualizationDragWidget::destroyed,
                [this]() { impl->m_HighlightedDragWidget = nullptr; });
    }

    impl->m_HighlightedDragWidget = dragWidget;
}

VisualizationDragWidget* DragDropGuiController::getHightlightedDragWidget() const
{
    return impl->m_HighlightedDragWidget;
}

void DragDropGuiController::delayedCloseWidget(QWidget* widget)
{
    widget->hide();
    impl->m_WidgetToClose << widget;
}

void DragDropGuiController::doCloseWidgets()
{
    for (auto widget : impl->m_WidgetToClose)
    {
        widget->close();
    }

    impl->m_WidgetToClose.clear();
}

bool DragDropGuiController::checkMimeDataForVisualization(
    const QMimeData* mimeData, VisualizationDragDropContainer* dropContainer)
{
    if (!mimeData || !dropContainer)
    {
        qCWarning(LOG_DragDropGuiController()) << QObject::tr(
            "DragDropGuiController::checkMimeDataForVisualization, invalid input parameters.");
        Q_ASSERT(false);
        return false;
    }

    auto result = false;

    if (mimeData->hasFormat(MIME_TYPE_VARIABLE_LIST))
    {
        auto variables = sqpApp->variableController().variables(
            Variable2::IDs(mimeData->data(MIME_TYPE_VARIABLE_LIST)));

        if (variables.size() == 1)
        {

            auto variable = variables[0];
            if (variable->data() != nullptr)
            {

                // Check that the variable is not already in a graph

                auto parent = dropContainer->parentWidget();
                while (parent && qobject_cast<VisualizationWidget*>(parent) == nullptr)
                {
                    parent = parent->parentWidget(); // Search for the top level VisualizationWidget
                }

                if (parent)
                {
                    auto visualizationWidget = static_cast<VisualizationWidget*>(parent);

                    FindVariableOperation findVariableOperation { variable };
                    visualizationWidget->accept(&findVariableOperation);
                    auto variableContainers = findVariableOperation.result();
                    if (variableContainers.empty())
                    {
                        result = true;
                    }
                    else
                    {
                        // result = false: the variable already exist in the visualisation
                    }
                }
                else
                {
                    qCWarning(LOG_DragDropGuiController()) << QObject::tr(
                        "DragDropGuiController::checkMimeDataForVisualization, the parent "
                        "VisualizationWidget cannot be found. Cannot check if the variable is "
                        "already used or not.");
                }
            }
            else
            {
                // result = false: the variable is not fully loaded
            }
        }
        else
        {
            // result = false: cannot drop multiple variables in the visualisation
        }
    }
    else if (mimeData->hasFormat(MIME_TYPE_PRODUCT_LIST))
    {
        auto productDataList = sqpApp->dataSourceController().productsDataForMimeData(
            mimeData->data(MIME_TYPE_PRODUCT_LIST));
        if (productDataList.count() == 1)
        {
            result = true;
        }
        else
        {
            // result = false: cannot drop multiple products in the visualisation
        }
    }
    else
    {
        // Other MIME data
        // no special rules, accepted by default
        result = true;
    }


    return result;
}
